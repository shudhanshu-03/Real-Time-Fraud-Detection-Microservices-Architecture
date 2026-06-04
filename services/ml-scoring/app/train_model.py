import numpy as np
import random
import joblib
from sklearn.ensemble import RandomForestClassifier

def generate_synthetic_data(num_samples=5000):
    X = []
    y = []
    
    # Feature order: amount, hour_of_day, time_since_last_transaction
    
    for _ in range(num_samples):
        # 10% chance of fraud in dataset to balance
        is_fraud = random.random() < 0.1
        
        if is_fraud:
            # Fraudulent patterns:
            # - Very high amounts (5000 - 20000)
            # - Late night hours (1 - 5 AM)
            # - Very short time since last tx (0 - 60 seconds)
            pattern_type = random.choice(['amount', 'time', 'velocity'])
            
            if pattern_type == 'amount':
                amount = random.uniform(5000, 20000)
                hour_of_day = random.randint(0, 23)
                time_since_last = random.uniform(3600, 86400)
            elif pattern_type == 'time':
                amount = random.uniform(10, 500)
                hour_of_day = random.randint(1, 5)
                time_since_last = random.uniform(3600, 86400)
            else:
                amount = random.uniform(10, 500)
                hour_of_day = random.randint(8, 20)
                time_since_last = random.uniform(0, 60)
            
            y.append(1)
        else:
            # Legitimate patterns
            amount = random.uniform(5, 1000)
            # Bias away from late night
            hour_of_day = random.choices([random.randint(0,5), random.randint(6,23)], weights=[0.1, 0.9])[0]
            time_since_last = random.uniform(3600, 259200) # 1 hour to 3 days
            
            y.append(0)
            
        X.append([amount, hour_of_day, time_since_last])
        
    return np.array(X), np.array(y)

def train():
    print("Generating synthetic data...")
    X, y = generate_synthetic_data()
    
    print("Training Random Forest...")
    clf = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
    clf.fit(X, y)
    
    print("Saving model to model.joblib...")
    joblib.dump(clf, "model.joblib")
    
    print("Training complete.")

if __name__ == '__main__':
    train()
