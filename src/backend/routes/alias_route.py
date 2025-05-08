from flask import Blueprint, request, jsonify
from src.backend.db import db
from src.backend.models.compare_model import CompanyGroup

alias_bp = Blueprint('alias_bp', __name__)

@alias_bp.route('/api/aliases', methods=['GET'])
def get_aliases():
    groups = CompanyGroup.query.all()
    return jsonify([
        {"id": group.id, "aliases": group.aliases} for group in groups
    ])

@alias_bp.route('/api/aliases', methods=['POST'])
def create_alias_group():
    data = request.get_json()
    aliases = data.get('aliases')
    if not aliases or not isinstance(aliases, list):
        return jsonify({"error": "Invalid aliases"}), 400

    # Normalize for case-insensitive match
    input_aliases = set(a.strip().lower() for a in aliases)
    all_groups = CompanyGroup.query.all()

    duplicates = []
    for group in all_groups:
        group_aliases = set(a.lower() for a in group.aliases)
        overlap = input_aliases.intersection(group_aliases)
        if overlap:
            duplicates.extend(overlap)

    if duplicates:
        return jsonify({"error": f"Duplicate alias(es) already exist: {', '.join(sorted(set(duplicates)))}"}), 400

    group = CompanyGroup(aliases=aliases)
    db.session.add(group)
    db.session.commit()
    return jsonify({"message": "Group created", "id": group.id}), 201


@alias_bp.route('/api/aliases/<int:group_id>', methods=['PUT'])
def update_alias_group(group_id):
    data = request.get_json()
    action = data.get('action')
    alias = data.get('alias')

    print(f"\n📥 PUT on /api/aliases/{group_id} | Action: {action}, Alias: {alias}")
    group = CompanyGroup.query.get(group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    if not isinstance(group.aliases, list):
        group.aliases = list(group.aliases)

    alias_lower = alias.strip().lower()

    if action == "add":
        # Check for duplicates in other groups
        other_groups = CompanyGroup.query.filter(CompanyGroup.id != group_id).all()
        for other in other_groups:
            if any(a.lower() == alias_lower for a in other.aliases):
                return jsonify({"error": f"Alias '{alias}' already exists in another group"}), 400

        if alias not in group.aliases:
            group.aliases.append(alias)
        else:
            return jsonify({"error": "Alias already exists in this group"}), 400

    elif action == "remove":
        if alias in group.aliases:
            group.aliases.remove(alias)
        else:
            return jsonify({"error": "Alias not found in this group"}), 400
    else:
        return jsonify({"error": "Invalid action"}), 400

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(group, "aliases")

    db.session.commit()
    return jsonify({"message": f"Alias {action}ed"}), 200




@alias_bp.route('/api/aliases/<int:group_id>', methods=['DELETE'])
def delete_alias_group(group_id):
    group = CompanyGroup.query.get(group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    db.session.delete(group)
    db.session.commit()
    return jsonify({"message": "Group deleted"}), 200
