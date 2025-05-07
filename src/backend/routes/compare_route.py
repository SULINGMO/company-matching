from flask import Blueprint, request, jsonify,render_template
from src.backend.models.compare_model import categorize_token, weights,CompanyGroup
from src.backend.simhash import calculate_weighted_simhash
from fuzzywuzzy import fuzz
import pandas as pd
from src.backend.db import db
import json

compare_bp = Blueprint('compare_bp', __name__, template_folder='templates')

@compare_bp.route('/upload', methods=['POST'])
def upload_file():
    if request.content_length and request.content_length > 5 * 1024 * 1024:
        return jsonify({"error": "File too large. Please upload a smaller file (<5MB)."}), 413

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

    def match_company_names(speaker_name, df_column, speaker_aliases, categorize_token, weights):
        matches = []
        for name in df_column:
            if speaker_name.strip().lower() == name.strip().lower():
                matches.append({'name': name, 'similarity': 2.0, 'fromAliasMatch': False})
                continue
            if name.strip() in speaker_aliases:
                matches.append({'name': name, 'similarity': 1.0, 'fromAliasMatch': True})
                continue
            similarity = calculate_weighted_simhash(speaker_name, name, categorize_token, weights)
            if similarity >= 0.7:
                matches.append({'name': name, 'similarity': round(similarity, 2), 'fromAliasMatch': False})
        return sorted(matches, key=lambda x: -x['similarity'])

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
        for group in company_groups:
            if speaker_name in group.aliases:
                speaker_aliases = group.aliases
                break

        for key in ['account', 'contact', 'linkedin', 'address']:
            if key in uploaded_files:
                df = uploaded_files[key]
                column = 'Account Name' if key in ['account', 'contact'] else 'Company'
                matches = match_company_names(speaker_name, df[column], speaker_aliases, categorize_token, weights)
                if matches:
                    if key == 'linkedin':
                        result[f'matched_{key}'] = matches[:5]
                    else:
                        result[f'matched_{key}'] = [matches[0]]

        if any(result[key] for key in ['matched_account', 'matched_contact', 'matched_linkedin', 'matched_address']):
            results.append(result)

    for result in results:
        all_similarities = [
            match['similarity'] for key in ['matched_account', 'matched_contact', 'matched_linkedin', 'matched_address']
            for match in result[key] if match.get('similarity')
        ]
        result['max_similarity'] = max(all_similarities) if all_similarities else 0

    results = sorted(results, key=lambda x: -x['max_similarity'])
    for result in results:
        result.pop('max_similarity', None)

    print(json.dumps(results, indent=2))
    return jsonify(results)


@compare_bp.route('/confirm', methods=['POST'])
def confirm_to_group():
    data = request.json
    speaker = data.get('speaker')
    fields = data.get('fields', [])

    if not speaker or not fields:
        return jsonify({"error": "Missing speaker or fields"}), 400

    # Build set of all aliases to add
    aliases_to_add = set([speaker])
    for field in fields:
        matched = data.get(f'matched_{field}')
        if isinstance(matched, list):
            aliases_to_add.update(matched)
        elif isinstance(matched, str):
            aliases_to_add.add(matched)

    print("✅ Aliases to add:", aliases_to_add)

    # Load all groups and find matches
    all_groups = CompanyGroup.query.all()
    matched_groups = [group for group in all_groups if any(alias in group.aliases for alias in aliases_to_add)]

    if not matched_groups:
        # No existing group → create new
        new_group = CompanyGroup(aliases=list(aliases_to_add))
        db.session.add(new_group)
        db.session.commit()
        return jsonify({"message": "New group created"}), 200

    # Merge all aliases and matched groups into one
    combined_aliases = set(aliases_to_add)
    for group in matched_groups:
        combined_aliases.update(group.aliases)

    # Keep one group and delete the rest
    primary_group = matched_groups[0]
    primary_group.aliases = list(combined_aliases)

    for group in matched_groups[1:]:
        db.session.delete(group)

    db.session.commit()
    return jsonify({"message": "Aliases merged into one group"}), 200



@compare_bp.route('/unconfirm', methods=['POST'])
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