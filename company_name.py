from flask import Flask, request, jsonify, render_template
import pandas as pd
from simhash import calculate_weighted_simhash, Simhash
from flask_sqlalchemy import SQLAlchemy
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

app = Flask(__name__, template_folder='templates')

# Configure the SQLAlchemy part of the app instance
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Create the SQLAlchemy db instance
db = SQLAlchemy(app)

# Define the ConfirmedMapping model
class ConfirmedMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    speaker = db.Column(db.String(255), nullable=False, unique=True)
    matched_account = db.Column(db.String(255))
    matched_contact = db.Column(db.String(255))

# Define keyword categories
COUNTRY_KEYWORDS = ["Singapore", "Indonesia", "Malaysia", "Philippines", "Thailand", "Vietnam"]
GROUP_COMPANY_KEYWORDS = ["Group", "Inc", "Corporation", "Ltd", "Limited", "Company", "Bank"]

# Define weights for each category
WEIGHTS = {
    'group': 0.3,
    'country': 0.6,
    'company': 1.0
}

# Function to categorize tokens
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

        record = ConfirmedMapping.query.filter_by(speaker=speaker_name).first()
        confirmed = {
            'account': record.matched_account if record else None,
            'contact': record.matched_contact if record else None
        }

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
            record = ConfirmedMapping.query.filter_by(speaker=speaker).first()
            if not record:
                record = ConfirmedMapping(speaker=speaker)
                db.session.add(record)

            if account is not None:
                record.matched_account = account
            if contact is not None:
                record.matched_contact = contact

    db.session.commit()
    return jsonify({"message": "Match(es) confirmed!"})

@app.route('/unconfirm', methods=['POST'])
def unconfirm_match():
    data = request.get_json()
    speaker = data.get('speaker')
    field = data.get('field')

    record = ConfirmedMapping.query.filter_by(speaker=speaker).first()
    if not record:
        return jsonify({"error": f"No mapping found for {speaker}"}), 404

    if field:
        if field == 'account':
            record.matched_account = None
        elif field == 'contact':
            record.matched_contact = None
    else:
        db.session.delete(record)

    db.session.commit()
    return jsonify({"message": f"{field or 'All'} unconfirmed for {speaker}"})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
