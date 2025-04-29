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


        speaker_aliases = []

        # Find aliases for this speaker if it exists
        for group in company_groups:
            if speaker_name in group.aliases:
                speaker_aliases = group.aliases
                break

        for key in ['account', 'contact', 'linkedin', 'address']:
            matches = []
            if key in uploaded_files:
                df = uploaded_files[key]
                column = 'Account Name' if key in ['account', 'contact'] else 'Company'

                # Step 1: Try matching uploaded file against database aliases (STRICT)
                for name in df[column]:
                    if name.strip() in speaker_aliases:
                        similarity = calculate_weighted_simhash(speaker_name, name, categorize_func=categorize_token,
                                                                weights=weights)
                        matches.append({
                            'name': name,
                            'similarity': round(similarity, 2),
                            'fromAliasMatch': True
                        })

                # Step 2: If no alias match, fallback to normal similarity match
                if not matches:
                    for name in df[column]:
                        similarity = calculate_weighted_simhash(speaker_name, name, categorize_func=categorize_token,
                                                                weights=weights)
                        if similarity >= 0.7:
                            matches.append({
                                'name': name,
                                'similarity': round(similarity, 2),
                                'fromAliasMatch': False
                            })

                matches = sorted(matches, key=lambda x: -x['similarity'])
                if matches:
                    if key == 'linkedin':
                        result[f'matched_{key}'] = matches[:5]  # top 5 for LinkedIn
                    else:
                        result[f'matched_{key}'] = [matches[0]]  # still show only 1 best for others

        # Only add result if there is any match
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
    print("DEBUG Incoming Payload:", data)  # 🔥 DEBUG PAYLOAD

    speaker = data.get('speaker')
    fields = data.get('fields', [])

    if not speaker or not fields:
        return jsonify({"error": "Missing speaker or fields"}), 400

    aliases_to_add = set([speaker])

    for field in fields:
        print(f"DEBUG Checking field: {field}")  # 🔥
        matched = data.get(f'matched_{field}')
        print(f"DEBUG Matched Value for {field}:", matched)  # 🔥

        if isinstance(matched, list):
            aliases_to_add.update(matched)
        elif isinstance(matched, str):
            aliases_to_add.add(matched)

    print("DEBUG Final Aliases to Add:", aliases_to_add)  # 🔥

    groups = CompanyGroup.query.all()
    target_group = None

    for group in groups:
        if any(alias in group.aliases for alias in aliases_to_add):
            target_group = group
            break

    if target_group:
        new_aliases = list(set(target_group.aliases + list(aliases_to_add)))
        target_group.aliases = new_aliases
        db.session.commit()
    else:
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

    aliases_to_remove = set()

    for field in fields:
        matched = data.get(f'matched_{field}')
        if isinstance(matched, list):
            aliases_to_remove.update(matched)
        elif isinstance(matched, str):
            aliases_to_remove.add(matched)

    groups = CompanyGroup.query.all()
    target_group = None

    for group in groups:
        if speaker in group.aliases:
            target_group = group
            break

    if not target_group:
        return jsonify({"error": "No matching group found to unconfirm"}), 400

    updated_aliases = [alias for alias in target_group.aliases if alias not in aliases_to_remove]

    if speaker not in updated_aliases:
        updated_aliases.append(speaker)

    if updated_aliases == [speaker]:
        db.session.delete(target_group)
        db.session.commit()
        return jsonify({"message": "Group deleted because only speaker left"}), 200
    else:
        target_group.aliases = updated_aliases
        db.session.commit()
        return jsonify({"message": "Selected aliases unconfirmed, speaker preserved"}), 200





if __name__ == '__main__':
    app.run(debug=True)
