import re
from typing import List, Dict, Tuple, Any

DEPARTMENTS = {
    "Computer Science and Engineering": ["cse", "computer science", "computer engineering"],
    "Artificial Intelligence and Data Science": ["aids", "ai & ds", "ai and ds", "artificial intelligence"],
    "Electronics and Communication Engineering": ["ece", "electronics and communication"],
    "Electrical and Electronics Engineering": ["eee", "electrical and electronics"],
    "Information Technology": ["it", "information technology"],
    "Civil Engineering": ["civil engineering", "civil"],
    "Mechanical Engineering": ["mechanical engineering", "mechanical"]
}

RECRUITERS = [
    "TCS", "Infosys", "Wipro", "Cognizant", "Accenture", "Zoho", "Amazon", "IBM", 
    "Capgemini", "HCL", "Soliton", "Mindtree", "Hexaware", "L&T Infotech"
]

CLUBS = [
    "Rotaract Club", "NSS", "NCC", "YRC", "Fine Arts Club", "Coding Club", 
    "Science Club", "Photography Club", "Drama Club", "Sports Club"
]

RESEARCH_AREAS = [
    "Machine Learning", "Deep Learning", "Internet of Things", "Cloud Computing", 
    "VLSI Design", "Power Systems", "Renewable Energy", "Smart Grids", "Wireless Networks",
    "Image Processing", "Cyber Security", "Data Data Analytics", "Thermal Engineering"
]

class EntityExtractor:
    def extract(self, page_id: int, title: str, url: str, page_type: str, content: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extract nodes (entities) and edges (relationships) from page contents."""
        entities: List[Dict[str, Any]] = [
            {"entity_type": "College", "name": "Sri Krishna College of Technology", "page_id": page_id},
            {"entity_type": "Page", "name": title, "page_id": page_id}
        ]
        
        relationships: List[Dict[str, Any]] = [
            self._rel("College", "Sri Krishna College of Technology", "HAS_PAGE", "Page", title, page_id)
        ]
        
        lowered = content.lower()
        
        # 1. Departments
        found_depts = []
        for dept_name, keywords in DEPARTMENTS.items():
            if any(kw in title.lower() or kw in lowered for kw in keywords):
                entities.append({"entity_type": "Department", "name": dept_name, "page_id": page_id})
                relationships.append(self._rel("Page", title, "MENTIONS", "Department", dept_name, page_id))
                relationships.append(self._rel("Department", dept_name, "PART_OF", "College", "Sri Krishna College of Technology", page_id))
                found_depts.append(dept_name)

        # 2. Recruiters / Companies
        for company in RECRUITERS:
            if re.search(r'\b' + re.escape(company.lower()) + r'\b', lowered):
                entities.append({"entity_type": "Company", "name": company, "page_id": page_id})
                relationships.append(self._rel("Page", title, "MENTIONS", "Company", company, page_id))
                
                # Relate company to college
                relationships.append(self._rel("Company", company, "RECRUITS_AT", "College", "Sri Krishna College of Technology", page_id))
                
                # Relate company to found departments on the page
                for dept in found_depts:
                    relationships.append(self._rel("Company", company, "HIRED_FROM", "Department", dept, page_id))

        # 3. Faculty members
        # Regex to catch Dr. Arun Kumar, Prof. Priya Raman, Mr. R. Rajesh etc.
        faculty_pattern = re.compile(r'\b(?:Dr|Prof|Mr|Ms|Mrs)\.?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z]\.?\s+[A-Z][a-zA-Z]+|\s+[A-Z][a-zA-Z]+){0,2}')
        raw_faculty = faculty_pattern.findall(content)
        seen_faculty = set()
        
        for faculty in raw_faculty:
            clean_name = re.sub(r'\s+', ' ', faculty).strip()
            if clean_name in seen_faculty or len(clean_name) > 40:
                continue
            seen_faculty.add(clean_name)
            entities.append({"entity_type": "Faculty", "name": clean_name, "page_id": page_id})
            relationships.append(self._rel("Page", title, "MENTIONS", "Faculty", clean_name, page_id))
            
            # Relate faculty to found departments
            for dept in found_depts:
                relationships.append(self._rel("Faculty", clean_name, "BELONGS_TO", "Department", dept, page_id))

        # 4. Courses / Degrees
        # Catch items like "B.E. Computer Science", "B.Tech. Information Technology", "M.B.A."
        course_pattern = re.compile(r'\b(?:B\.E\.|B\.Tech\.|M\.E\.|M\.Tech\.|M\.B\.A\.|M\.C\.A\.|Ph\.D\.)\s+[A-Z][a-zA-Z\s&]+')
        raw_courses = course_pattern.findall(content)
        seen_courses = set()
        for course in raw_courses:
            clean_course = re.sub(r'\s+', ' ', course).strip()
            # Trim trailing filler words
            clean_course = re.split(r'\b(?:and|is|offers|for|in)\b', clean_course, flags=re.IGNORECASE)[0].strip()
            if clean_course in seen_courses or len(clean_course) < 6 or len(clean_course) > 60:
                continue
            seen_courses.add(clean_course)
            entities.append({"entity_type": "Course", "name": clean_course, "page_id": page_id})
            relationships.append(self._rel("Page", title, "MENTIONS", "Course", clean_course, page_id))
            
            # Offer relationship
            for dept in found_depts:
                relationships.append(self._rel("Department", dept, "OFFERS", "Course", clean_course, page_id))

        # 5. Labs
        lab_pattern = re.compile(r'\b[A-Z][a-zA-Z0-9\s-]{3,40}\s+(?:Lab|Laboratory)\b')
        raw_labs = lab_pattern.findall(content)
        seen_labs = set()
        for lab in raw_labs:
            clean_lab = re.sub(r'\s+', ' ', lab).strip()
            if clean_lab in seen_labs or len(clean_lab) > 50:
                continue
            seen_labs.add(clean_lab)
            entities.append({"entity_type": "Lab", "name": clean_lab, "page_id": page_id})
            relationships.append(self._rel("Page", title, "MENTIONS", "Lab", clean_lab, page_id))
            
            for dept in found_depts:
                relationships.append(self._rel("Lab", clean_lab, "FACILITY_OF", "Department", dept, page_id))

        # 6. Research Areas
        for r_area in RESEARCH_AREAS:
            if re.search(r'\b' + re.escape(r_area.lower()) + r'\b', lowered):
                entities.append({"entity_type": "Research Area", "name": r_area, "page_id": page_id})
                relationships.append(self._rel("Page", title, "MENTIONS", "Research Area", r_area, page_id))
                
                for dept in found_depts:
                    relationships.append(self._rel("Department", dept, "RESEARCHES_IN", "Research Area", r_area, page_id))

        # 7. Clubs
        for club in CLUBS:
            if club.lower() in lowered:
                entities.append({"entity_type": "Club", "name": club, "page_id": page_id})
                relationships.append(self._rel("Page", title, "MENTIONS", "Club", club, page_id))
                relationships.append(self._rel("Club", club, "ACTIVE_IN", "College", "Sri Krishna College of Technology", page_id))

        # 8. Events (Conferences, symposiums, workshops)
        if page_type == "event" or "symposium" in lowered or "workshop on" in lowered or "conference on" in lowered:
            event_name = title
            # Clean up event name
            if len(event_name) > 70:
                event_name = event_name[:67] + "..."
            entities.append({"entity_type": "Event", "name": event_name, "page_id": page_id})
            relationships.append(self._rel("Page", title, "MENTIONS", "Event", event_name, page_id))
            
            for dept in found_depts:
                relationships.append(self._rel("Event", event_name, "ORGANIZED_BY", "Department", dept, page_id))

        # Deduplicate
        entities = self._dedupe_entities(entities)
        relationships = self._dedupe_relationships(relationships)
        
        return entities, relationships

    def _rel(self, src_type: str, src_name: str, rel_type: str, tgt_type: str, tgt_name: str, page_id: int) -> Dict[str, Any]:
        return {
            "source_type": src_type,
            "source_name": src_name,
            "relationship_type": rel_type,
            "target_type": tgt_type,
            "target_name": tgt_name,
            "page_id": page_id
        }

    def _dedupe_entities(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        res = []
        for x in items:
            k = (x["entity_type"], x["name"].strip(), x["page_id"])
            if k not in seen:
                seen.add(k)
                res.append(x)
        return res

    def _dedupe_relationships(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        res = []
        for x in items:
            k = (
                x["source_type"], x["source_name"].strip(), 
                x["relationship_type"], 
                x["target_type"], x["target_name"].strip(), 
                x["page_id"]
            )
            if k not in seen:
                seen.add(k)
                res.append(x)
        return res
