# ml_engine.py
import numpy as np
import pandas as pd # type: ignore
from sklearn.ensemble import IsolationForest # type: ignore
from sklearn.preprocessing import StandardScaler # type: ignore
from datetime import datetime, timedelta

class FraudDetector:
    """
    Analyzes employee activity logs using Isolation Forest to detect anomalies
    and potential fraud/slacking behavior.
    """
    def __init__(self):
        self.model = IsolationForest(
            n_estimators=100,
            contamination=0.1,  # Assuming 10% of the population might be anomalous
            random_state=42,
            max_samples='auto'
        )
        self.scaler = StandardScaler()
        self.is_fitted = False
        
        # Keywords used to flag non-work related applications
        self.distracting_keywords = [
            'youtube', 'reddit', 'netflix', 'game', 'social', 
            'facebook', 'twitter', 'instagram', 'discord', 'steam', 
            'tiktok', 'hulu', 'prime video', 'spotify', 'telegram'
        ]

    def prepare_features(self, activity_data):
        """
        Transforms raw activity log dictionaries into a structured NumPy array 
        of numerical features for the ML model.
        
        Includes new feature: non_work_app_flag based on window title.
        """
        if not activity_data:
            return None

        df = pd.DataFrame(activity_data)

        features = []
        for _, row in df.iterrows():
            idle_time = float(row.get('idle_time', 0))
            mouse_activity = float(row.get('mouse_activity', 0))
            keyboard_activity = float(row.get('keyboard_activity', 0))
            hour = float(row.get('hour', 12))
            
            # Process Window Title ---
            active_window_title = str(row.get('active_window_title', '')).lower()
            
            # Feature engineering for contextual data
            ip_hash = hash(str(row.get('ip_address', ''))) % 1000
            device_hash = hash(str(row.get('device_id', ''))) % 1000

            total_activity = mouse_activity + keyboard_activity
            # A measure of the time spent idle relative to total measured time
            idle_ratio = idle_time / (idle_time + total_activity + 1)

            # Feature: Is activity happening outside the 8 AM - 6 PM window?
            is_after_hours = 1 if hour < 8 or hour > 18 else 0
            
            # NEW FEATURE: Flag if the active window title contains a distracting keyword
            non_work_app_flag = 1 if any(keyword in active_window_title for keyword in self.distracting_keywords) else 0

            features.append([
                idle_time,
                mouse_activity,
                keyboard_activity,
                hour,
                ip_hash,
                device_hash,
                idle_ratio,
                is_after_hours,
                total_activity,
                non_work_app_flag  # The crucial new feature
            ])

        return np.array(features)

    def fit(self, activity_data):
        """Fits the Isolation Forest model and the StandardScaler."""
        features = self.prepare_features(activity_data)

        if features is None or len(features) < 10:
            # Need a minimum number of samples to train the model effectively
            return False

        try:
            scaled_features = self.scaler.fit_transform(features)
            self.model.fit(scaled_features)
            self.is_fitted = True
            return True
        except ValueError as e:
            print(f"Error during ML model fitting (likely due to insufficient or non-numeric data): {e}")
            self.is_fitted = False
            return False

    def predict_anomaly(self, activity_data):
        """Predicts anomaly scores for a given batch of activity data."""
        if not self.is_fitted:
            return {'is_anomaly': False, 'anomaly_score': 0.0}

        features = self.prepare_features(activity_data)

        if features is None or len(features) == 0:
            return {'is_anomaly': False, 'anomaly_score': 0.0}

        scaled_features = self.scaler.transform(features)

        # Get anomaly scores (closer to 1 is normal, closer to -1 is anomalous)
        scores = self.model.score_samples(scaled_features)
        predictions = self.model.predict(scaled_features)
        
        avg_score = np.mean(scores)
        # Calculate the ratio of data points flagged as an anomaly (-1)
        anomaly_ratio = np.sum(predictions == -1) / len(predictions)

        # Normalize the raw score to a 0-100 risk score (higher is worse)
        # 1.0 (perfectly normal) -> 0, -1.0 (highly anomalous) -> 100
        # We use +0.5 to center the typical range around zero for better scaling
        normalized_score = max(0, min(100, (1 - (avg_score + 0.5)) * 100))

        return {
            'is_anomaly': anomaly_ratio > 0.3, # Flag as anomaly if >30% of recent events are flagged
            'anomaly_score': float(normalized_score),
            'anomaly_ratio': float(anomaly_ratio)
        }

    def analyze_and_flag(self, db, employee_id):
        """
        Fetches recent activity, runs the ML model, and creates a fraud alert 
        in the database if a high-risk anomaly is detected.
        """
        activity_data = db.get_employee_activity_for_ml(employee_id)

        if not activity_data or len(activity_data) < 5:
            return None

        # Fit model on the available data before predicting
        self.fit(activity_data)

        recent_data = activity_data[:10]
        result = self.predict_anomaly(recent_data)

        # Identify human-readable risk factors
        factors = self._identify_risk_factors(recent_data)

        risk_score = result['anomaly_score']

        if result['is_anomaly'] and risk_score > 60:
            if risk_score >= 80:
                alert_level = 'High'
            elif risk_score >= 50:
                alert_level = 'Medium'
            else:
                alert_level = 'Low'

            description = self._generate_alert_description(factors)
            db.create_fraud_alert(employee_id, risk_score, alert_level, description)

        return {
            'risk_score': risk_score,
            'alert_level': 'High' if risk_score >= 80 else 'Medium' if risk_score >= 50 else 'Low',
            'factors': factors
        }

    def get_risk_score(self, db, employee_id):
        """
        Provides the current risk score and human-readable factors for the 
        Employee Report dashboard without necessarily creating an alert.
        """
        activity_data = db.get_employee_activity_for_ml(employee_id)

        if not activity_data or len(activity_data) < 5:
            return {
                'risk_score': 0,
                'alert_level': 'Low',
                'factors': []
            }

        self.fit(activity_data)

        result = self.predict_anomaly(activity_data[:10])
        factors = self._identify_risk_factors(activity_data[:10])

        risk_score = result['anomaly_score']

        if risk_score >= 80:
            alert_level = 'High'
        elif risk_score >= 50:
            alert_level = 'Medium'
        else:
            alert_level = 'Low'

        return {
            'risk_score': round(risk_score, 2),
            'alert_level': alert_level,
            'factors': factors
        }

    def _identify_risk_factors(self, activity_data):
        """
        Checks for specific, rule-based risk factors in the recent activity logs.
        """
        if not activity_data:
            return []

        factors = []
        df = pd.DataFrame(activity_data)
        
        # 1. NEW RISK FACTOR: Distracting Application Usage
        if 'active_window_title' in df.columns:
            # Count logs where the window title contains any distracting keyword
            distracting_logs = df['active_window_title'].apply(
                lambda x: 1 if any(k in str(x).lower() for k in self.distracting_keywords) else 0
            ).sum()
            
            if len(df) > 0:
                distracting_ratio = distracting_logs / len(df)
                if distracting_ratio > 0.3:
                    factors.append({
                        'type': 'Distracting App Use',
                        'severity': 'high' if distracting_ratio > 0.5 else 'medium',
                        'description': f'{distracting_logs} out of {len(df)} recent logs show foreground use of non-work applications (e.g., social media, streaming).'
                    })
        
        # 2. High Idle Time
        if 'idle_time' in df.columns:
            avg_idle = df['idle_time'].mean()
            if avg_idle > 45: # Threshold in seconds
                factors.append({
                    'type': 'High Idle Time',
                    'severity': 'high' if avg_idle > 60 else 'medium',
                    'description': f'Average idle time of {avg_idle:.0f} seconds exceeds normal threshold (low physical input).'
                })

        # 3. After Hours Activity
        if 'hour' in df.columns:
            after_hours = df[df['hour'].apply(lambda x: x < 8 or x > 18)]
            if len(after_hours) > len(df) * 0.3:
                factors.append({
                    'type': 'After Hours Activity',
                    'severity': 'medium',
                    'description': 'Significant activity detected outside normal business hours (8AM-6PM).'
                })

        # 4. IP/Device Mismatch (Requires comprehensive login log data)
        if 'ip_address' in df.columns:
            unique_ips = df['ip_address'].nunique()
            if unique_ips > 3:
                factors.append({
                    'type': 'IP Mismatch',
                    'severity': 'high',
                    'description': f'Multiple IP addresses ({unique_ips}) detected in recent sessions, indicating a change in working location.'
                })

        if 'device_id' in df.columns:
            unique_devices = df['device_id'].nunique()
            if unique_devices > 2:
                factors.append({
                    'type': 'Device Anomaly',
                    'severity': 'medium',
                    'description': f'Multiple devices ({unique_devices}) used in recent sessions.'
                })
        
        # 5. Irregular Activity Patterns (High Variance)
        if 'mouse_activity' in df.columns and 'keyboard_activity' in df.columns:
            total_activity = df['mouse_activity'] + df['keyboard_activity']
            activity_std = total_activity.std()
            activity_mean = total_activity.mean()

            # High variance relative to the mean indicates spiky, irregular input
            if activity_mean > 0 and activity_std / activity_mean > 1.5:
                factors.append({
                    'type': 'Pattern Deviation',
                    'severity': 'medium',
                    'description': 'Irregular activity patterns detected (high variance in mouse/keyboard inputs).'
                })

        return factors

    def _generate_alert_description(self, factors):
        """Generates a concise alert summary based on the highest severity factor."""
        if not factors:
            return 'Anomalous behavior detected by ML model'

        high_severity = [f for f in factors if f['severity'] == 'high']

        if high_severity:
            # Prioritize a high-severity factor if available
            return high_severity[0]['description']

        # Otherwise, take the most common or first medium/low factor
        return factors[0]['description']