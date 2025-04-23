from flask import Flask, request, jsonify, render_template
import pandas as pd
import json
from simhash import calculate_weighted_simhash, Simhash

app = Flask(__name__, template_folder='templates')

# Load or initialize confirmed mappings
try:
    with open('confirmed_mappings.json', 'r') as f:
        confirmed_mappings = json.load(f)
except FileNotFoundError:
    confirmed_mappings = {}

COUNTRY_KEYWORDS = ["Singapore", "Indonesia", "Malaysia", "Philippines", "Thailand", "Vietnam"]
GROUP_COMPANY_KEYWORDS = ["Group", "Inc", "Corporation", "Ltd", "Limited", "Company", "Bank"]

WEIGHTS = {
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
    if 'speaker' not in request.files or 'account' not in request.files or 'contact' not in request.files:
        return jsonify({"error": "Please upload all three files: speaker, account, and contact lists."}), 400

    speaker_file = request.files['speaker']
    account_file = request.files['account']
    contact_file = request.files['contact']

    try:
        speaker_df = pd.read_excel(speaker_file)
        account_df = pd.read_excel(account_file)
        contact_df = pd.read_excel(contact_file)
    except Exception as e:
        return jsonify({"error": f"Error reading files: {str(e)}"}), 500

    results = []
    account_names = account_df['Account Name'].dropna().unique()
    contact_names = contact_df['Account Name'].dropna().unique()

    seen_speakers = set()

    for _, row in speaker_df.iterrows():
        speaker_name = str(row.get('Company', '')).strip()
        if not speaker_name or speaker_name in seen_speakers:
            continue

        seen_speakers.add(speaker_name)

        speaker_simhash = calculate_weighted_simhash(speaker_name, categorize_token, WEIGHTS)

        top_account_match = None
        top_account_similarity = 0
        for account in account_names:
            account_simhash = calculate_weighted_simhash(account, categorize_token, WEIGHTS)
            similarity = 1 - bin(speaker_simhash ^ account_simhash).count('1') / 128
            if similarity > top_account_similarity:
                top_account_similarity = similarity
                top_account_match = {'account': account, 'similarity': round(similarity * 100, 2)}

        top_contact_match = None
        top_contact_similarity = 0
        for contact in contact_names:
            contact_simhash = calculate_weighted_simhash(contact, categorize_token, WEIGHTS)
            similarity = 1 - bin(speaker_simhash ^ contact_simhash).count('1') / 128
            if similarity > top_contact_similarity:
                top_contact_similarity = similarity
                top_contact_match = {'contact': contact, 'similarity': round(similarity * 100, 2)}

        confirmed = confirmed_mappings.get(speaker_name, {})

        # Only include if either similarity is above 70%
        if (top_account_match and top_account_match['similarity'] > 70) or \
           (top_contact_match and top_contact_match['similarity'] > 70):
            results.append({
                'speaker': speaker_name,
                'matched_account': top_account_match,
                'matched_contact': top_contact_match,
                'confirmed': confirmed
            })

    results.sort(key=lambda x: max(
        x['matched_account']['similarity'] if x['matched_account'] else 0,
        x['matched_contact']['similarity'] if x['matched_contact'] else 0
    ), reverse=True)

    return jsonify(results)

@app.route('/confirm', methods=['POST'])
def confirm_match():
    data = request.get_json()
    if isinstance(data, dict):
        data = [data]

    for match in data:
        speaker = match.get('speaker')
        account = match.get('account')
        contact = match.get('contact')
        if speaker:
            if speaker not in confirmed_mappings:
                confirmed_mappings[speaker] = {}
            if account is not None:
                confirmed_mappings[speaker]['account'] = account
            if contact is not None:
                confirmed_mappings[speaker]['contact'] = contact

    with open('confirmed_mappings.json', 'w') as f:
        json.dump(confirmed_mappings, f, indent=2)

    return jsonify({"message": "Match(es) confirmed!"})

@app.route('/unconfirm', methods=['POST'])
def unconfirm_match():
    data = request.get_json()
    speaker = data.get('speaker')
    field = data.get('field')  # optional: 'account' or 'contact'

    if not speaker:
        return jsonify({"error": "Speaker is required"}), 400

    if speaker not in confirmed_mappings:
        return jsonify({"error": f"No mapping found for {speaker}."}), 404

    fields_to_remove = []

    if field:  # Only one field to unconfirm
        if field in confirmed_mappings[speaker]:
            fields_to_remove.append(field)
        else:
            return jsonify({"error": f"{field} not found for {speaker}."}), 404
    else:  # No field specified: unconfirm both
        fields_to_remove = list(confirmed_mappings[speaker].keys())

    for f in fields_to_remove:
        del confirmed_mappings[speaker][f]

    if not confirmed_mappings[speaker]:  # Remove speaker if empty
        del confirmed_mappings[speaker]

    with open('confirmed_mappings.json', 'w') as f:
        json.dump(confirmed_mappings, f, indent=2)

    removed_fields = ', '.join([f.capitalize() for f in fields_to_remove])
    return jsonify({"message": f"{removed_fields} unconfirmed for {speaker}"})

if __name__ == '__main__':
    app.run(debug=True)
