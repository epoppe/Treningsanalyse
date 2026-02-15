"""
Service for å eksportere data i ulike formater.
"""

import json
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import zipfile
import shutil

from app.database.session import SessionLocal
from app.database.models.activity import Activity

class ExportService:
    """Service for dataeksport."""
    
    def __init__(self, export_dir: str = "exports"):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(exist_ok=True)
    
    def export_activities_to_csv(self, activities: List[Activity], filename: Optional[str] = None) -> str:
        """Eksporter aktiviteter til CSV."""
        if not filename:
            filename = f"activities_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        filepath = self.export_dir / filename
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Header
            writer.writerow([
                'ID', 'Navn', 'Type', 'Startdato', 'Varighet', 'Distanse', 
                'Kalorier', 'Gjennomsnittspuls', 'Makspuls', 'Høydemeter'
            ])
            
            # Data
            for activity in activities:
                writer.writerow([
                    activity.activity_id,
                    activity.activity_name,
                    activity.activity_type.type_name if activity.activity_type else '',
                    activity.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                    activity.duration,
                    activity.distance,
                    activity.calories,
                    activity.average_heart_rate,
                    activity.max_heart_rate,
                    activity.total_ascent
                ])
        
        return str(filepath)
    
    def export_activities_to_json(self, activities: List[Activity], filename: Optional[str] = None) -> str:
        """Eksporter aktiviteter til JSON."""
        if not filename:
            filename = f"activities_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.export_dir / filename
        
        activities_data = []
        for activity in activities:
            activities_data.append({
                'id': activity.activity_id,
                'name': activity.activity_name,
                'type': activity.activity_type.type_name if activity.activity_type else None,
                'start_time': activity.start_time.isoformat(),
                'duration': activity.duration,
                'distance': activity.distance,
                'calories': activity.calories,
                'average_heart_rate': activity.average_heart_rate,
                'max_heart_rate': activity.max_heart_rate,
                'total_ascent': activity.total_ascent,
                'total_descent': activity.total_descent
            })
        
        with open(filepath, 'w', encoding='utf-8') as jsonfile:
            json.dump(activities_data, jsonfile, indent=2, ensure_ascii=False)
        
        return str(filepath)
    
    def export_activity_to_tcx(self, activity: Activity, detailed_data: List[Dict[str, Any]]) -> str:
        """Eksporter en aktivitet til TCX-format."""
        filename = f"activity_{activity.activity_id}_{datetime.now().strftime('%Y%m%d')}.tcx"
        filepath = self.export_dir / filename
        
        # Opprett TCX XML-struktur
        root = ET.Element("TrainingCenterDatabase")
        root.set("xmlns", "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2")
        
        activities_elem = ET.SubElement(root, "Activities")
        activity_elem = ET.SubElement(activities_elem, "Activity")
        activity_elem.set("Sport", "Running")  # Kan gjøres dynamisk
        
        # Aktivitets-ID
        id_elem = ET.SubElement(activity_elem, "Id")
        id_elem.text = activity.start_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        
        # Lap
        lap_elem = ET.SubElement(activity_elem, "Lap")
        lap_elem.set("StartTime", activity.start_time.strftime('%Y-%m-%dT%H:%M:%S.000Z'))
        
        # Lap-statistikk
        ET.SubElement(lap_elem, "TotalTimeSeconds").text = str(activity.duration or 0)
        ET.SubElement(lap_elem, "DistanceMeters").text = str(activity.distance or 0)
        ET.SubElement(lap_elem, "Calories").text = str(activity.calories or 0)
        
        if activity.average_heart_rate:
            avg_hr_elem = ET.SubElement(lap_elem, "AverageHeartRateBpm")
            ET.SubElement(avg_hr_elem, "Value").text = str(activity.average_heart_rate)
        
        if activity.max_heart_rate:
            max_hr_elem = ET.SubElement(lap_elem, "MaximumHeartRateBpm")
            ET.SubElement(max_hr_elem, "Value").text = str(activity.max_heart_rate)
        
        # Track med detaljerte data
        if detailed_data:
            track_elem = ET.SubElement(lap_elem, "Track")
            
            for point in detailed_data:
                trackpoint_elem = ET.SubElement(track_elem, "Trackpoint")
                
                if 'timestamp' in point:
                    ET.SubElement(trackpoint_elem, "Time").text = point['timestamp']
                
                if 'latitude' in point and 'longitude' in point:
                    position_elem = ET.SubElement(trackpoint_elem, "Position")
                    ET.SubElement(position_elem, "LatitudeDegrees").text = str(point['latitude'])
                    ET.SubElement(position_elem, "LongitudeDegrees").text = str(point['longitude'])
                
                if 'altitude' in point:
                    ET.SubElement(trackpoint_elem, "AltitudeMeters").text = str(point['altitude'])
                
                if 'distance' in point:
                    ET.SubElement(trackpoint_elem, "DistanceMeters").text = str(point['distance'])
                
                if 'heart_rate' in point:
                    hr_elem = ET.SubElement(trackpoint_elem, "HeartRateBpm")
                    ET.SubElement(hr_elem, "Value").text = str(point['heart_rate'])
        
        # Skriv til fil
        tree = ET.ElementTree(root)
        tree.write(filepath, encoding='utf-8', xml_declaration=True)
        
        return str(filepath)
    
    def create_backup(self, include_exports: bool = True) -> str:
        """Opprett backup av alle data."""
        backup_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        backup_path = self.export_dir / backup_filename
        
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Backup database (portabel sti: backend/data/treningsanalyse.db)
            backend_dir = Path(__file__).resolve().parent.parent.parent
            db_path = backend_dir / "data" / "treningsanalyse.db"
            if db_path.exists():
                zipf.write(db_path, "database/treningsanalyse.db")
            
            # Backup data-filer
            data_dir = backend_dir / "data"
            if data_dir.exists():
                for file_path in data_dir.rglob("*"):
                    if file_path.is_file():
                        zipf.write(file_path, f"data/{file_path.relative_to(data_dir)}")
            
            # Backup eksporter hvis ønsket
            if include_exports and self.export_dir.exists():
                for file_path in self.export_dir.rglob("*"):
                    if file_path.is_file() and file_path != backup_path:
                        zipf.write(file_path, f"exports/{file_path.relative_to(self.export_dir)}")
        
        return str(backup_path)

# Global export service
export_service = ExportService() 