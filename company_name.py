from flask import Flask, request, jsonify, render_template
import pandas as pd
from simhash import calculate_weighted_simhash
from flask_sqlalchemy import SQLAlchemy
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

app = Flask(__name__, template_folder='templates')

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize DB
db = SQLAlchemy(app)

# Define model
class ConfirmedMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    speaker = db.Column(db.String(255), nullable=False, unique=True)
    matched_account = db.Column(db.String(255))
    matched_contact = db.Column(db.String(255))
    matched_linkedin = db.Column(db.String(255))
    matched_address = db.Column(db.String(255))

# Keywords for matching
COUNTRY_KEYWORDS = ["Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda", "Argentina",
                    "Armenia", "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh",
                    "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bhutan", "Bolivia", "Bosnia and Herzegovina",
                    "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cabo Verde",
                    "Cambodia", "Cameroon", "Canada", "Central African Republic", "Chad", "Chile", "China",
                    "Colombia", "Comoros", "Congo (Congo-Brazzaville)", "Costa Rica", "Croatia", "Cuba",
                    "Cyprus", "Czech Republic", "Democratic Republic of the Congo", "Denmark", "Djibouti",
                    "Dominica", "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea",
                    "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia",
                    "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala", "Guinea", "Guinea-Bissau",
                    "Guyana", "Haiti", "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq",
                    "Ireland", "Israel", "Italy", "Ivory Coast", "Jamaica", "Japan", "Jordan", "Kazakhstan",
                    "Kenya", "Kiribati", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia",
                    "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar", "Malawi", "Malaysia",
                    "Maldives", "Mali", "Malta", "Marshall Islands", "Mauritania", "Mauritius", "Mexico",
                    "Micronesia", "Moldova", "Monaco", "Mongolia", "Montenegro", "Morocco", "Mozambique",
                    "Myanmar (Burma)", "Namibia", "Nauru", "Nepal", "Netherlands", "New Zealand", "Nicaragua",
                    "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", "Palau",
                    "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland",
                    "Portugal", "Qatar", "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia",
                    "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Sao Tome and Principe", "Saudi Arabia",
                    "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Slovenia",
                    "Solomon Islands", "Somalia", "South Africa", "South Korea", "South Sudan", "Spain", "Sri Lanka",
                    "Sudan", "Suriname", "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania",
                    "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey",
                    "Turkmenistan", "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom",
                    "United States", "Uruguay", "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela", "Vietnam",
                    "Yemen", "Zambia", "Zimbabwe"]

GROUP_COMPANY_KEYWORDS = ["Group", "Inc", "Incorporated", "Corporation", "Corp", "Co", "Company", "Ltd", "Limited",
                          "LLC", "LLP", "PLC", "Bank", "Holdings", "Holding", "Partners", "Partnership", "Trust",
                          "Association", "Foundation", "Sdn Bhd", "Pte Ltd", "AG", "GmbH", "BV", "NV", "SAS", "SA",
                          "SpA", "AB", "AS", "Oy", "A/S", "K.K.", "Bhd", "Tbk", "Enterprises", "International",
                          "Industries", "Tech", "Technologies", "Solutions", "Services", "Global"]



# Weights
weights = {
    'group': 0.3,
    'country': 0.6,
    'company': 1.0
}

# Token categorization function
def categorize_token(token):
    token = token.lower()
    if any(country.lower() in token for country in COUNTRY_KEYWORDS):
        return 'country'
    if any(group.lower() in token for group in GROUP_COMPANY_KEYWORDS):
        return 'group'
    return 'company'

@app.route('/')
def index():
    return render_template('company_name.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    uploaded_files = {}
    speaker_file = request.files.get('speaker')
    if not speaker_file:
        return jsonify({"error": "Speaker list is required"}), 400

    try:
        df = pd.read_excel(speaker_file)
        df = df.dropna(subset=['Company'])
        df = df.drop_duplicates(subset=['Company'])
        uploaded_files['speaker'] = df

    except Exception as e:
        return jsonify({"error": f"Error reading speaker file: {str(e)}"}), 500

    # Load other files (account, contact, linkedin, address)
    for key in ['account', 'contact', 'linkedin', 'address']:
        file = request.files.get(key)
        if file:
            try:
                df = pd.read_excel(file)
                if key in ['account', 'contact']:
                    df = df.dropna(subset=['Account Name'])
                else:
                    df = df.dropna(subset=['Company'])
                uploaded_files[key] = df
            except Exception as e:
                return jsonify({"error": f"Error reading file {key}: {str(e)}"}), 500

    # Initialize all_names to store unique company names from all files
    all_names = {}
    for key, df in uploaded_files.items():
        if key in ['account', 'contact']:
            all_names[key] = df['Account Name'].dropna().unique()
        else:
            all_names[key] = df['Company'].dropna().unique()

    results = []

    # Process each speaker entry
    for _, speaker in uploaded_files['speaker'].iterrows():
        speaker_name = speaker['Company']
        result = {
            'speaker': speaker_name,
            'matched_account': [],
            'matched_contact': [],
            'matched_linkedin': [],
            'matched_address': []
        }

        # Initialize match_results with empty lists for valid keys (no 'speaker' key here)
        match_results = {
            'account': [],
            'contact': [],
            'linkedin': [],
            'address': []
        }

        # Compare speaker name with names from other lists (account, contact, etc.)
        for key, names in all_names.items():
            # Only compare if the key is one of the matchable categories
            if key not in match_results:
                continue  # Skip any irrelevant keys

            for name in names:
                if speaker_name == name:
                    continue  # Skip exact matches (same name)

                # Calculate similarity for non-matching names
                similarity = calculate_weighted_simhash(
                    speaker_name, name, categorize_func=categorize_token, weights=weights
                )
                if similarity >= 0.65:
                    match_results[key].append({
                        'name': name,
                        'similarity': round(similarity, 2)
                    })
        # Only keep the top match from each list (if similarity >= 0.65)
        for key in ['account', 'contact', 'linkedin', 'address']:
            matches = sorted(match_results[key], key=lambda x: -x['similarity'])
            if matches and matches[0]['similarity'] >= 0.65:
                result[f'matched_{key}'] = [matches[0]]
            else:
                result[f'matched_{key}'] = []


        # Only append result if there are any matches
        if any(result[key] for key in ['matched_account', 'matched_contact', 'matched_linkedin', 'matched_address']):
            results.append(result)

    # Filter results to only include entries with valid matches
    # Only append result if there are any matches (similarity can now be less than 1)
    results = [
        result for result in results
        if any(match.get('similarity', 0) >= 0.65 for match in
               result['matched_account'] + result['matched_contact'] + result['matched_linkedin'] + result[
                   'matched_address'])
    ]

    # Print results for debugging
    # Add a max similarity score to each result for sorting
    for result in results:
        all_similarities = [
            match['similarity'] for key in ['matched_account', 'matched_contact', 'matched_linkedin', 'matched_address']
            for match in result[key] if match.get('similarity')
        ]
        result['max_similarity'] = max(all_similarities) if all_similarities else 0

    # Sort results by max similarity in descending order
    results = sorted(results, key=lambda x: -x['max_similarity'])

    # Optionally remove the helper field before returning
    for result in results:
        result.pop('max_similarity', None)

    import json
    print(json.dumps(results, indent=2))

    return jsonify(results)


@app.route('/confirm', methods=['POST'])
def confirm_mapping():
    data = request.json
    try:
        for mapping in data.get('mappings', []):
            new_mapping = ConfirmedMapping(
                speaker=mapping['speaker'],
                matched_account=mapping.get('matched_account'),
                matched_contact=mapping.get('matched_contact'),
                matched_linkedin=mapping.get('matched_linkedin'),
                matched_address=mapping.get('matched_address')
            )
            db.session.add(new_mapping)
        db.session.commit()
        return jsonify({"message": "Mappings confirmed successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error confirming mappings: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)
