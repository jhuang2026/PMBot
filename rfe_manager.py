import os
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

class RFEGuidelinesManager:
    """Manager for RFE guidelines and templates"""
    
    def __init__(self, guidelines_file_path: str = "RFE_Issue_Description_Guidelines.md"):
        self.guidelines_file_path = guidelines_file_path
        self.guidelines_content = self._load_guidelines()
        self.rfe_types = {
            "Infrastructure/Platform": {
                "focus": "System capabilities, integration, and compatibility",
                "emphasis": "Technical specifications, performance requirements, platform support",
                "required_sections": ["Technical Requirements", "Dependencies", "Non-functional Requirements"],
                "description": "Hardware, operators, platform support, system-level capabilities"
            },
            "Feature Enhancement": {
                "focus": "User capabilities and improved workflows", 
                "emphasis": "User value, experience improvements, business impact",
                "required_sections": ["User Stories", "Success Criteria", "User Value"],
                "description": "New user capabilities, UI improvements, workflow enhancements"
            },
            "Integration": {
                "focus": "Connectivity, data flow, and interoperability",
                "emphasis": "Security, compliance, dependency management", 
                "required_sections": ["Dependencies", "Security Requirements", "Integration Points"],
                "description": "External service connections, APIs, data flow, interoperability"
            },
            "Documentation/Process": {
                "focus": "Knowledge transfer and process improvement",
                "emphasis": "User guidance, accessibility, maintenance",
                "required_sections": ["Scope Definition", "User Impact"],
                "description": "Documentation improvements, process changes, tooling"
            }
        }
    
    def _load_guidelines(self) -> str:
        """Load RFE guidelines from file"""
        try:
            if os.path.exists(self.guidelines_file_path):
                with open(self.guidelines_file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                logger.warning(f"Guidelines file not found: {self.guidelines_file_path}")
                return self._get_default_guidelines()
        except Exception as e:
            logger.error(f"Error loading guidelines: {e}")
            return self._get_default_guidelines()
    
    def _get_default_guidelines(self) -> str:
        """Default RFE guidelines if file not found"""
        return """
# RFE Issue Description Guidelines

## Required Sections

### Problem Statement
*Problem Statement:* 
Clearly articulate the problem or gap that needs to be addressed. Include quantified impact where possible.

### User Value/Goal
*User Value:* 
Explain the value proposition and desired outcome. What business value does this provide?

### Scope Definition
*Scope:*

**In Scope:**
* Specific capabilities to be implemented

**Out of Scope:**
* What will NOT be included

**Future Considerations:**
* Potential future enhancements

### Description/Overview
*Description:* 
Provide a comprehensive overview of the proposed solution

### Success Criteria
*Success Criteria:*
* Specific, measurable criteria with metrics
* Performance benchmarks where applicable
* Functional requirements

## Best Practices
- Use specific, measurable language with metrics
- Focus on user needs and business value
- Include concrete examples and context
- Balance technical and business considerations
- Follow proper formatting (*Section Name:*)
"""
    
    def get_rfe_template(self, rfe_type: str) -> str:
        """Generate RFE template based on type"""
        template = f"""# RFE Template - {rfe_type}

## Required Sections

### Problem Statement
*Problem Statement:* 
[Clearly articulate the problem or gap that needs to be addressed. Include quantified impact where possible.]

### User Value/Goal
*User Value:* 
[Explain the value proposition and desired outcome. What business value does this provide?]

### Scope Definition
*Scope:*

**In Scope:**
* [Specific capabilities to be implemented]

**Out of Scope:**
* [What will NOT be included]

**Future Considerations:**
* [Potential future enhancements]

### Description/Overview
*Description:* 
[Provide a comprehensive overview of the proposed solution]

### Success Criteria
*Success Criteria:*
* [Specific, measurable criteria with metrics]
* [Performance benchmarks where applicable]
* [Functional requirements]

## Type-Specific Sections for {rfe_type}

"""
        
        if rfe_type in self.rfe_types:
            type_info = self.rfe_types[rfe_type]
            template += f"**Focus:** {type_info['focus']}\n"
            template += f"**Emphasis:** {type_info['emphasis']}\n"
            template += f"**Description:** {type_info['description']}\n\n"
            
            for section in type_info['required_sections']:
                template += f"### {section}\n*{section}:* \n[Add relevant details for {section.lower()}]\n\n"
        
        template += """## Optional Sections (Add as needed)

### User Stories
*User Stories:*
As a [user type], I want [capability], so that [benefit]

### Technical Requirements
*Technical Requirements:*
* [Performance requirements]
* [Compatibility requirements]
* [Security requirements]

### Dependencies
*Dependencies:*
* [Hardware/software dependencies]
* [External service dependencies]

### Security Requirements
*Security Requirements:*
* [Authentication/authorization needs]
* [Data protection requirements]
* [Compliance considerations]

### Non-functional Requirements
*Non-functional Requirements:*
* [Performance benchmarks]
* [Scalability requirements]
* [Availability requirements]

### Integration Points
*Integration Points:*
* [External systems to integrate with]
* [APIs to be developed/consumed]
* [Data flow requirements]

### Related Links
*Related Links:*
* [Supporting documentation]
* [Industry standards]
* [Related RFEs or issues]

---

## Validation Checklist
- [ ] Problem statement clearly defines the issue
- [ ] User value is quantified with business impact
- [ ] Scope is clearly defined (in/out/future)
- [ ] Description provides comprehensive solution overview
- [ ] Success criteria are specific and measurable
- [ ] Type-specific sections are completed
- [ ] Technical requirements are specified
- [ ] Dependencies are identified
"""
        
        return template
    
    def validate_rfe(self, rfe_content: str) -> Dict[str, List[str]]:
        """Validate RFE content against guidelines"""
        validation_results = {
            "missing_required": [],
            "suggestions": [],
            "strengths": [],
            "score": 0
        }
        
        required_sections = [
            "Problem Statement",
            "User Value", 
            "Scope",
            "Description",
            "Success Criteria"
        ]
        
        content_lower = rfe_content.lower()
        score = 0
        
        # Check required sections
        for section in required_sections:
            if section.lower() in content_lower:
                score += 20  # 100 points total for required sections
                validation_results["strengths"].append(f"Contains {section} section")
            else:
                validation_results["missing_required"].append(section)
        
        # Check for best practices (bonus points)
        if "measurable" in content_lower or "metric" in content_lower:
            validation_results["strengths"].append("Contains measurable criteria")
            score += 5
        else:
            validation_results["suggestions"].append("Consider adding measurable success criteria with specific metrics")
        
        if "user" in content_lower and ("value" in content_lower or "benefit" in content_lower):
            validation_results["strengths"].append("Includes user value proposition")
            score += 5
        else:
            validation_results["suggestions"].append("Consider adding more detailed user value and business impact")
        
        if "scope" in content_lower and ("out of scope" in content_lower or "not include" in content_lower):
            validation_results["strengths"].append("Clearly defines scope boundaries")
            score += 5
        else:
            validation_results["suggestions"].append("Consider adding 'Out of Scope' section to clarify boundaries")
        
        if len(rfe_content.split()) < 100:
            validation_results["suggestions"].append("Consider adding more detailed description (current content seems brief)")
        elif len(rfe_content.split()) > 200:
            validation_results["strengths"].append("Comprehensive and detailed content")
            score += 5
        
        # Check for technical depth
        technical_keywords = ["requirement", "specification", "performance", "security", "integration", "dependency"]
        technical_mentions = sum(1 for keyword in technical_keywords if keyword in content_lower)
        if technical_mentions >= 3:
            validation_results["strengths"].append("Good technical depth")
            score += 5
        else:
            validation_results["suggestions"].append("Consider adding more technical details and requirements")
        
        # Check for business context
        business_keywords = ["business", "value", "impact", "benefit", "customer", "user", "cost", "revenue"]
        business_mentions = sum(1 for keyword in business_keywords if keyword in content_lower)
        if business_mentions >= 3:
            validation_results["strengths"].append("Good business context")
            score += 5
        else:
            validation_results["suggestions"].append("Consider adding more business context and value proposition")
        
        validation_results["score"] = min(score, 100)  # Cap at 100
        
        return validation_results
    
    def get_rfe_improvement_suggestions(self, rfe_content: str, rfe_type: str = None) -> List[str]:
        """Get specific improvement suggestions for an RFE"""
        suggestions = []
        content_lower = rfe_content.lower()
        
        # Type-specific suggestions
        if rfe_type and rfe_type in self.rfe_types:
            type_info = self.rfe_types[rfe_type]
            
            if rfe_type == "Infrastructure/Platform":
                if "performance" not in content_lower:
                    suggestions.append("Add performance requirements and benchmarks")
                if "compatibility" not in content_lower:
                    suggestions.append("Specify platform compatibility requirements")
                if "scalability" not in content_lower:
                    suggestions.append("Consider scalability requirements")
            
            elif rfe_type == "Feature Enhancement":
                if "user story" not in content_lower and "as a" not in content_lower:
                    suggestions.append("Add user stories in 'As a [user], I want [feature], so that [benefit]' format")
                if "workflow" not in content_lower:
                    suggestions.append("Describe how this improves user workflows")
            
            elif rfe_type == "Integration":
                if "security" not in content_lower:
                    suggestions.append("Add security requirements for integrations")
                if "api" not in content_lower:
                    suggestions.append("Specify API requirements and specifications")
                if "authentication" not in content_lower:
                    suggestions.append("Consider authentication and authorization requirements")
            
            elif rfe_type == "Documentation/Process":
                if "audience" not in content_lower:
                    suggestions.append("Clearly define the target audience")
                if "maintenance" not in content_lower:
                    suggestions.append("Consider ongoing maintenance requirements")
        
        # General improvements
        if "example" not in content_lower and "for example" not in content_lower:
            suggestions.append("Add concrete examples to illustrate the requirements")
        
        if "timeline" not in content_lower and "deadline" not in content_lower:
            suggestions.append("Consider adding timeline or deadline information")
        
        if "risk" not in content_lower:
            suggestions.append("Consider identifying potential risks and mitigation strategies")
        
        return suggestions
    
    def get_rfe_type_recommendation(self, description: str) -> str:
        """Recommend RFE type based on description"""
        description_lower = description.lower()
        
        # Keywords for each type
        type_keywords = {
            "Infrastructure/Platform": [
                "hardware", "platform", "system", "infrastructure", "operator", 
                "cluster", "node", "performance", "scalability", "compatibility"
            ],
            "Feature Enhancement": [
                "user", "interface", "ui", "ux", "workflow", "feature", "capability",
                "dashboard", "visualization", "usability", "experience"
            ],
            "Integration": [
                "integration", "api", "connect", "external", "service", "data flow",
                "interoperability", "third-party", "sync", "import", "export"
            ],
            "Documentation/Process": [
                "documentation", "guide", "tutorial", "process", "procedure",
                "training", "knowledge", "manual", "help", "instruction"
            ]
        }
        
        # Score each type
        type_scores = {}
        for rfe_type, keywords in type_keywords.items():
            score = sum(1 for keyword in keywords if keyword in description_lower)
            type_scores[rfe_type] = score
        
        # Return type with highest score, or Feature Enhancement as default
        if max(type_scores.values()) > 0:
            return max(type_scores, key=type_scores.get)
        else:
            return "Feature Enhancement"