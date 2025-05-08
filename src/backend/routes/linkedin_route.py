from flask import Blueprint, request, jsonify, render_template
from src.backend.models.compare_model import categorize_token, weights, CompanyGroup
from src.backend.simhash import calculate_weighted_simhash
import pandas as pd
import json
from src.backend.db import db

linkedin_bp = Blueprint('linkedin_bp', __name__, template_folder='templates')


@linkedin_bp.route('/upload-linkedin', methods=['POST'])
def upload_linkedin():
    uploaded_files = {}
    linkedin_file = request.files.get('linkedin')
    if not linkedin_file:
        return jsonify({"error": "LinkedIn list is required"}), 400

    try:
        df = pd.read_excel(linkedin_file)
        df = df.dropna(subset=['Company']).drop_duplicates(subset=['Company'])
        uploaded_files['linkedin'] = df
    except Exception as e:
        return jsonify({"error": f"Error reading LinkedIn file: {str(e)}"}), 500

    for key in ['contact', 'address']:
        file = request.files.get(key)
        if file:
            try:
                df = pd.read_excel(file)
                column = 'Account Name' if key == 'contact' else 'Company'
                df = df.dropna(subset=[column])
                uploaded_files[key] = df
            except Exception as e:
                return jsonify({"error": f"Error reading file {key}: {str(e)}"}), 500

    company_groups = CompanyGroup.query.all()
    results = perform_matching(uploaded_files['linkedin'], 'linkedin', uploaded_files, company_groups)
    return jsonify(results)


def perform_matching(source_df, source_key, uploaded_files, company_groups):
    results = []
    seen_aliases = set()

    for _, source in source_df.iterrows():
        source_name = source['Company']

        # Skip if this company (or its alias) has already been handled
        if source_name in seen_aliases:
            continue

        result = {
            source_key: source_name,
            'matched_contact': [],
            'matched_address': [],
            'matched_linkedin_similar': []
        }

        source_aliases = []
        for group in company_groups:
            if source_name in group.aliases:
                source_aliases = group.aliases
                seen_aliases.update(group.aliases)
                break
        else:
            seen_aliases.add(source_name)

        for key in ['contact', 'address']:
            if key not in uploaded_files:
                continue

            matches = []
            df = uploaded_files[key]
            column = 'Account Name' if key == 'contact' else 'Company'

            for name in df[column]:
                if source_name.strip().lower() == name.strip().lower():
                    matches.append({'name': name, 'similarity': 2.0, 'fromAliasMatch': False})

            if not matches:
                for name in df[column]:
                    if name.strip() in source_aliases:
                        similarity = calculate_weighted_simhash(source_name, name, categorize_token, weights)
                        matches.append({'name': name, 'similarity': round(similarity, 2), 'fromAliasMatch': True})

            if not matches:
                for name in df[column]:
                    similarity = calculate_weighted_simhash(source_name, name, categorize_token, weights)
                    if similarity >= 0.7:
                        matches.append({'name': name, 'similarity': round(similarity, 2), 'fromAliasMatch': False})

            matches = sorted(matches, key=lambda x: -x['similarity'])
            if matches:
                result[f'matched_{key}'] = [matches[0]]

        # ✅ SimHash-based LinkedIn-to-LinkedIn similarity (no exact)
        if 'linkedin' in uploaded_files:
            df_linkedin = uploaded_files['linkedin']
            similar_matches = []

            # Get aliases for current source_name only
            source_aliases = []
            for group in company_groups:
                if source_name in group.aliases:
                    source_aliases = group.aliases
                    break

            for alt_name in df_linkedin['Company'].dropna().unique():
                alt_name_clean = str(alt_name).strip()
                current_name_clean = str(source_name).strip()

                if alt_name_clean.lower() == current_name_clean.lower():
                    continue  # skip exact match

                similarity = calculate_weighted_simhash(source_name, alt_name, categorize_token, weights)
                if similarity > 0.7 and similarity < 2.0:
                    is_alias = alt_name in source_aliases

                    similar_matches.append({
                        'name': alt_name,
                        'similarity': round(similarity, 2),
                        'fromAliasMatch': is_alias
                    })

            result['matched_linkedin_similar'] = sorted(similar_matches, key=lambda x: -x['similarity'])[:5]

        # Only include if anything was matched
        if any(result[key] for key in ['matched_contact', 'matched_address', 'matched_linkedin_similar']):
            results.append(result)

    # Sorting by highest similarity across all match types
    for result in results:
        all_similarities = [
            match['similarity']
            for key in ['matched_contact', 'matched_address', 'matched_linkedin_similar']
            for match in result.get(key, []) if match.get('similarity')
        ]
        result['max_similarity'] = max(all_similarities) if all_similarities else 0

    results = sorted(results, key=lambda x: -x['max_similarity'])
    for result in results:
        result.pop('max_similarity', None)

    print(json.dumps(results, indent=2))
    return results