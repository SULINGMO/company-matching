from flask_sqlalchemy import SQLAlchemy
from src.backend.db import db

# Example model using db through current_app
class CompanyGroup(db.Model):
    __tablename__ = 'company_groups'
    id = db.Column(db.Integer, primary_key=True)
    aliases = db.Column(db.ARRAY(db.Text), nullable=False)
