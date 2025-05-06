from flask import Blueprint, request, jsonify, send_file
import pandas as pd
from fuzzywuzzy import fuzz
from src.backend.models.compare_model import CompanyGroup
from src.backend.db import db
import ast
import math
from io import BytesIO

match_bp = Blueprint('match_bp', __name__)

# Global cache for unmatched results
latest_unmatched = []

def read_file_as_df(file_key):
    file = request.files.get(file_key)
    if file:
        try:
            df = pd.read_excel(file)
            df.columns = df.columns.astype(str).str.strip()
            print(f"\n📁 [{file_key.upper()}] Columns:", df.columns.tolist())
            return df.dropna(how='all')
        except Exception as e:
            print(f"❌ Error reading {file_key}:", e)
    return pd.DataFrame()

def find_all_matching_rows(df, match_columns, target_name):
    target_lower = target_name.lower().strip()
    matched_rows = []
    for _, row in df.iterrows():
        for col in match_columns:
            if col in df.columns:
                cell_value = str(row[col]).strip().lower()
                if target_lower == cell_value or fuzz.ratio(target_lower, cell_value) == 100:
                    matched_rows.append(row)
                    break
    return matched_rows

def clean_nan(obj):
    if isinstance(obj, float) and math.isnan(obj):
        return None
    elif isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    else:
        return obj

@match_bp.route('/match_data', methods=['POST'])
def match_data():
    global latest_unmatched

    try:
        speaker_df = pd.read_excel(request.files['speaker'])
        speaker_df = speaker_df.dropna(subset=['Company']).drop_duplicates(subset=['Company'])
    except Exception as e:
        return jsonify({'error': f'Error reading speaker file: {e}'}), 400

    contact_df = read_file_as_df('contact')
    account_df = read_file_as_df('account')
    address_df = read_file_as_df('address')
    linkedin_df = read_file_as_df('linkedin')

    company_groups = CompanyGroup.query.all()
    alias_groups = []
    for group in company_groups:
        try:
            aliases = group.aliases
            if isinstance(aliases, str):
                aliases = ast.literal_eval(aliases)
            alias_group = [alias.strip() for alias in aliases]
            alias_groups.append(alias_group)
        except Exception as e:
            print(f"⚠️ Could not parse aliases for group ID {group.id}: {group.aliases}")
    print(f"✅ Loaded {len(alias_groups)} alias groups.")

    results = []
    matched_companies = []

    for _, row in speaker_df.iterrows():
        company = row['Company'].strip()
        matched_alias_group = None

        for alias_group in alias_groups:
            if any(
                company.lower() == alias.lower() or
                fuzz.ratio(company.lower(), alias.lower()) == 100
                for alias in alias_group
            ):
                matched_alias_group = alias_group
                break

        matched_names = matched_alias_group if matched_alias_group else [company]

        all_sources = [
            (contact_df, ['Account Name']),
            (account_df, ['Account Name']),
            (address_df, ['Company']),
            (linkedin_df, ['Company'])
        ]

        match_found = False
        for df, match_cols in all_sources:
            for name in matched_names:
                matching_rows = find_all_matching_rows(df, match_cols, name)
                for match_row in matching_rows:
                    enriched = {'Company': company}
                    enriched.update(match_row.to_dict())

                    if 'Full Name' in enriched and enriched['Full Name']:
                        enriched['Name'] = enriched['Full Name']
                    elif enriched.get('First Name') or enriched.get('Last Name'):
                        first = enriched.get('First Name') or ''
                        last = enriched.get('Last Name') or ''
                        enriched['Name'] = f"{first} {last}".strip()

                    ordered = {'Company': enriched['Company']}
                    if 'Name' in enriched:
                        ordered['Name'] = enriched['Name']
                    for key, value in enriched.items():
                        if key not in ['Company', 'Name']:
                            ordered[key] = value

                    results.append(ordered)
                    match_found = True

        if match_found:
            matched_companies.append(company)

    unmatched = []
    for _, row in speaker_df.iterrows():
        company = row['Company'].strip()
        if company not in matched_companies:
            unmatched.append(row.to_dict())

    cleaned_results = [clean_nan(row) for row in results]
    unmatched_clean = [clean_nan(row) for row in unmatched]
    latest_unmatched = unmatched_clean

    accept_header = request.headers.get("Accept", "").lower()
    if "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in accept_header:
        df = pd.DataFrame(cleaned_results)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Matched Data')
        output.seek(0)
        return send_file(
            output,
            download_name="matched_data.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    return jsonify({
        "matched": cleaned_results,
        "unmatched": unmatched_clean
    }), 200

@match_bp.route('/download_unmatched', methods=['GET'])
def download_unmatched():
    global latest_unmatched

    if not latest_unmatched:
        return jsonify({"error": "No unmatched data available."}), 400

    df = pd.DataFrame(latest_unmatched)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Unmatched Data')
    output.seek(0)

    return send_file(
        output,
        download_name="unmatched_data.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
