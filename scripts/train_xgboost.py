"""
Synthetic data generator and XGBoost model trainer for Predictive Injury Modeling.
"""

import json
import os
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score
import structlog

logger = structlog.get_logger()

# Set random seed for reproducibility
np.random.seed(42)

def generate_synthetic_data(num_samples=10000):
    """
    Generate synthetic historical training data with a realistic injury distribution.
    Features:
    - load_change_pct: -50% to +100%
    - days_since_rest: 0 to 30
    - hr_drift_pct: -5% to +15%
    - recovery_proxy: 0.0 to 1.0
    """
    logger.info(f"Generating {num_samples} synthetic samples...")
    
    load_change_pct = np.random.normal(0, 20, num_samples)
    days_since_rest = np.random.exponential(5, num_samples).astype(int)
    hr_drift_pct = np.random.normal(2, 3, num_samples)
    recovery_proxy = np.clip(np.random.normal(0.7, 0.2, num_samples), 0.0, 1.0)
    
    # Feature matrix
    X = np.column_stack((load_change_pct, days_since_rest, hr_drift_pct, recovery_proxy))
    
    # Generate labels (injury_next_14_days) based on heuristics + noise
    # Higher risk if: load spike, many days without rest, high HR drift, low recovery
    risk_score = (
        (load_change_pct > 25).astype(float) * 0.3 +
        (days_since_rest > 10).astype(float) * 0.2 +
        (hr_drift_pct > 5).astype(float) * 0.25 +
        (recovery_proxy < 0.4).astype(float) * 0.25
    )
    
    # Add random noise
    risk_score += np.random.normal(0, 0.1, num_samples)
    
    # 1 if injury, 0 if healthy
    y = (risk_score > 0.5).astype(int)
    
    injury_rate = np.mean(y)
    logger.info(f"Generated data with an injury rate of {injury_rate * 100:.1f}%")
    
    return X, y

def train_model(X, y):
    """Train the XGBClassifier."""
    logger.info("Splitting dataset...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    logger.info("Training XGBoost Classifier...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        objective='binary:logistic',
        use_label_encoder=False,
        eval_metric='logloss'
    )
    
    model.fit(X_train, y_train)
    
    logger.info("Evaluating model...")
    y_pred = model.predict(X_test)
    
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    
    logger.info(f"Model Accuracy: {acc:.3f}")
    logger.info(f"Model Precision: {prec:.3f}")
    logger.info(f"Model Recall: {rec:.3f}")
    
    return model

def save_model(model, filepath):
    """Save the model to JSON format."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    model.save_model(filepath)
    logger.info(f"Model saved successfully to {filepath}")

if __name__ == "__main__":
    X, y = generate_synthetic_data()
    model = train_model(X, y)
    
    model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "models", "xgboost_injury_model.json")
    save_model(model, model_path)
