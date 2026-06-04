import os
import joblib
import numpy as np

class MockModelEngine:
    """
    A trained ML Model Engine.
    Loads a Random Forest model from model.joblib.
    """
    
    def __init__(self):
        self.model_version = "rf-v1"
        self.confidence_base = 0.90
        
        model_path = os.path.join(os.path.dirname(__file__), "..", "model.joblib")
        if os.path.exists(model_path):
            self.model = joblib.load(model_path)
            self.is_loaded = True
        else:
            print(f"Warning: Model not found at {model_path}. Run train_model.py first.")
            self.model = None
            self.is_loaded = False

    def predict(self, request):
        if not self.is_loaded:
            return {
                "score": 0.05,
                "flags": ["MODEL_NOT_LOADED"],
                "model_version": "fallback",
                "confidence": 0.0,
                "feature_importances": {}
            }
            
        # Extract features in the same order as training: amount, hour_of_day, time_since_last_transaction
        features = np.array([[
            request.amount, 
            request.hour_of_day, 
            request.time_since_last_transaction
        ]])
        
        # Get probability of fraud (class 1)
        score = self.model.predict_proba(features)[0][1]
        
        flags = []
        importances = {}
        
        # We can extract feature importances from the RF model
        if hasattr(self.model, 'feature_importances_'):
            importances = {
                "amount": float(self.model.feature_importances_[0]),
                "hour_of_day": float(self.model.feature_importances_[1]),
                "time_since_last_transaction": float(self.model.feature_importances_[2])
            }
            
        if score > 0.5:
            flags.append("HIGH_RISK_SCORE")
            if request.amount > 5000:
                flags.append("UNUSUAL_AMOUNT")
            if request.time_since_last_transaction < 60:
                flags.append("VELOCITY_SPIKE")
            if request.hour_of_day >= 1 and request.hour_of_day <= 5:
                flags.append("TIME_ANOMALY")

        return {
            "score": float(score),
            "flags": flags,
            "model_version": self.model_version,
            "confidence": self.confidence_base,
            "feature_importances": importances
        }
