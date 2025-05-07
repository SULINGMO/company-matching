from flask import Flask,render_template
import os
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from src.backend.models.compare_model import CompanyGroup
from src.backend.db import db

# Load environment variables

load_dotenv()

# Create an app factory function
def create_app():
    app = Flask(__name__, template_folder='src/public')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    from src.backend.models.compare_model import categorize_token, weights
    from src.backend.routes.compare_route import compare_bp
    from src.backend.routes.match_route import match_bp 
    app.register_blueprint(compare_bp)
    app.register_blueprint(match_bp)

    @app.route('/compare')
    def compare():
        return render_template('compare_name.html')
    @app.route('/match')
    def match():
        return render_template('match_data.html')
    return app


   

if __name__ == '__main__':
    app = create_app()  # ✅ Use the properly configured app
    print(app.url_map)  # Optional: confirm all routes
    app.run(debug=True)

