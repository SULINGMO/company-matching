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

    group = CompanyGroup(aliases=aliases)
    db.session.add(group)
    db.session.commit()
    return jsonify({"message": "Group created", "id": group.id}), 201

@alias_bp.route('/api/aliases/<int:group_id>', methods=['PUT'])
def update_alias_group(group_id):
    data = request.get_json()
    action = data.get('action')
    alias = data.get('alias')

    print(f"\n📥 Received PUT request on /api/aliases/{group_id}")
    print(f"   Action: {action}")
    print(f"   Alias: {alias}")

    group = CompanyGroup.query.get(group_id)
    if not group:
        print("❌ Group not found")
        return jsonify({"error": "Group not found"}), 404

    print(f"🧠 Group Found: ID {group.id}")
    print(f"   Current Aliases: {group.aliases}")

    if not isinstance(group.aliases, list):
        group.aliases = list(group.aliases)

    if action == "add":
        if alias not in group.aliases:
            group.aliases.append(alias)
            print(f"✅ Alias added → {alias}")
        else:
            print(f"⚠️ Alias already exists → {alias}")
            return jsonify({"error": "Alias already exists"}), 400

    elif action == "remove":
        if alias in group.aliases:
            group.aliases.remove(alias)
            print(f"🗑 Alias removed → {alias}")
        else:
            print(f"⚠️ Alias not found → {alias}")
            return jsonify({"error": "Alias not found"}), 400

    else:
        print("❌ Invalid action")
        return jsonify({"error": "Invalid action"}), 400

    # 🔧 Force SQLAlchemy to track list changes
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(group, "aliases")

    print(f"💾 Updated Aliases: {group.aliases}")
    db.session.commit()
    print("✅ DB Commit Successful")

    return jsonify({"message": f"Alias {action}ed"}), 200



@alias_bp.route('/api/aliases/<int:group_id>', methods=['DELETE'])
def delete_alias_group(group_id):
    group = CompanyGroup.query.get(group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    db.session.delete(group)
    db.session.commit()
    return jsonify({"message": "Group deleted"}), 200
