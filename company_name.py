from flask import Flask, request, jsonify, render_template
import pandas as pd
from simhash import calculate_weighted_simhash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import ARRAY
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

app = Flask(__name__, template_folder='templates')

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Updated Model ---
class CompanyGroup(db.Model):
    __tablename__ = 'company_groups'
    id = db.Column(db.Integer, primary_key=True)
    aliases = db.Column(ARRAY(db.Text), nullable=False)

# Keywords for categorization
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
                          "LLC", "LLP", "PLC", "Bank", "Holdings", "Holding", "Partners"]

weights = {
    'group': 0.3,
    'country': 0.6,
    'company': 1.0
}

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
        df = df.dropna(subset=['Company']).drop_duplicates(subset=['Company'])
        uploaded_files['speaker'] = df
    except Exception as e:
        return jsonify({"error": f"Error reading speaker file: {str(e)}"}), 500

    for key in ['account', 'contact', 'linkedin', 'address']:
        file = request.files.get(key)
        if file:
            try:
                df = pd.read_excel(file)
                column = 'Account Name' if key in ['account', 'contact'] else 'Company'
                df = df.dropna(subset=[column])
                uploaded_files[key] = df
            except Exception as e:
                return jsonify({"error": f"Error reading file {key}: {str(e)}"}), 500

    # Build fallback dataset from uploaded files
    all_names = {}
    for key, df in uploaded_files.items():
        if key == 'speaker':
            continue
        column = 'Account Name' if key in ['account', 'contact'] else 'Company'
        all_names[key] = df[column].dropna().unique()

    results = []
    company_groups = CompanyGroup.query.all()

    for _, speaker in uploaded_files['speaker'].iterrows():
        speaker_name = speaker['Company']
        result = {
            'speaker': speaker_name,
            'matched_account': [],
            'matched_contact': [],
            'matched_linkedin': [],
            'matched_address': []
        }

        matched_from_group = False

        # Step 1: Try match from existing company_groups
        for group in company_groups:
            for alias in group.aliases:
                similarity = calculate_weighted_simhash(
                    speaker_name, alias,
                    categorize_func=categorize_token,
                    weights=weights
                )
                if similarity >= 0.65:
                    for key in ['matched_account', 'matched_contact', 'matched_linkedin', 'matched_address']:
                        result[key] = [{
                            'name': alias,
                            'similarity': round(similarity, 2)
                        }]
                    matched_from_group = True
                    break
            if matched_from_group:
                break

        # Step 2: Fallback to file-based matching if no match in group
        if not matched_from_group:
            for key, names in all_names.items():
                matches = []
                for name in names:
                    if speaker_name == name:
                        continue
                    similarity = calculate_weighted_simhash(
                        speaker_name, name,
                        categorize_func=categorize_token,
                        weights=weights
                    )
                    if similarity >= 0.65:
                        matches.append({
                            'name': name,
                            'similarity': round(similarity, 2)
                        })
                matches = sorted(matches, key=lambda x: -x['similarity'])
                if matches:
                    result[f'matched_{key}'] = [matches[0]]

        # Append result if there is any match
        if any(result[key] for key in ['matched_account', 'matched_contact', 'matched_linkedin', 'matched_address']):
            results.append(result)

    # Sort results by max similarity
    for result in results:
        all_similarities = [
            match['similarity'] for key in ['matched_account', 'matched_contact', 'matched_linkedin', 'matched_address']
            for match in result[key] if match.get('similarity')
        ]
        result['max_similarity'] = max(all_similarities) if all_similarities else 0

    results = sorted(results, key=lambda x: -x['max_similarity'])

    for result in results:
        result.pop('max_similarity', None)

    import json
    print(json.dumps(results, indent=2))
    return jsonify(results)

@app.route('/confirm', methods=['POST'])
def confirm_to_group():
    data = request.json
    speaker = data.get('speaker')
    fields = data.get('fields', [])

    if not speaker or not fields:
        return jsonify({"error": "Missing speaker or fields"}), 400

    # Combine all matched values
    aliases_to_add = set([speaker])
    for field in fields:
        matched = data.get(f'matched_{field}')
        if matched:
            aliases_to_add.add(matched)

    # Load all current groups
    groups = CompanyGroup.query.all()

    # Step 1: Try to find a group that contains any alias (or speaker)
    target_group = None
    for group in groups:
        if any(alias in group.aliases for alias in aliases_to_add):
            target_group = group
            break

    if target_group:
        # Add all aliases that are not already in the group
        new_aliases = list(set(group.aliases + list(aliases_to_add)))
        target_group.aliases = new_aliases
        db.session.commit()
    else:
        # Create new group if no match found
        new_group = CompanyGroup(aliases=list(aliases_to_add))
        db.session.add(new_group)
        db.session.commit()

    return jsonify({"message": "Speaker and matched names added into one group"}), 200

@app.route('/unconfirm', methods=['POST'])
def unconfirm_from_group():
    data = request.json
    speaker = data.get('speaker')
    fields = data.get('fields', [])

    if not speaker or not fields:
        return jsonify({"error": "Missing speaker or fields"}), 400

    # Collect aliases to remove (only matched ones)
    aliases_to_remove = set()
    for field in fields:
        matched = data.get(f'matched_{field}')
        if matched:
            aliases_to_remove.add(matched)

    groups = CompanyGroup.query.all()
    target_group = None

    for group in groups:
        if speaker in group.aliases:
            target_group = group
            break

    if not target_group:
        return jsonify({"error": "No matching group found to unconfirm"}), 400

    # Logic: remove only the matched names, NOT speaker yet
    updated_aliases = [alias for alias in target_group.aliases if alias not in aliases_to_remove]

    if speaker not in updated_aliases:
        # Special case: if somehow speaker was also marked for removal manually
        updated_aliases.append(speaker)

    # Now check if speaker is the only one left
    if updated_aliases == [speaker]:
        # Only speaker left after removal, so delete entire group
        db.session.delete(target_group)
        db.session.commit()
        return jsonify({"message": "Group deleted because only speaker left"}), 200
    else:
        # Otherwise update normally
        target_group.aliases = updated_aliases
        db.session.commit()
        return jsonify({"message": "Selected aliases unconfirmed, speaker preserved"}), 200




if __name__ == '__main__':
    app.run(debug=True)
