import os
import ssl
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai_tools import TavilySearchTool

# System Setup
load_dotenv()
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except:
    pass

# --- CONFIGURATION ---
TOPIC = "The future of pediatric telehealth reimbursement in Florida" # EDIT THIS
PEERS = "CHOP, Texas Children's"

# Tools
search_tool = TavilySearchTool()

# Agents
researcher = Agent(
    role='Lead Researcher',
    goal=f'Analyze {TOPIC} for NCHS leadership.',
    backstory='Senior Research Analyst at Nicklaus Children\'s Health System.',
    tools=[search_tool],
    verbose=True
)

writer = Agent(
    role='Executive Writer',
    goal='Summarize findings into a professional report.',
    backstory='Director of Strategic Communications at NCHS.',
    verbose=True
)

# Tasks
t1 = Task(
    description=f"Research {TOPIC} focusing on {PEERS}.",
    expected_output="Detailed research findings.",
    agent=researcher
)

t2 = Task(
    description=f"Draft a board-ready memo on {TOPIC}.",
    expected_output="A professional markdown memo with '##' headers.",
    agent=writer,
    context=[t1]
)

# Execution
if __name__ == "__main__":
    nchs_crew = Crew(agents=[researcher, writer], tasks=[t1, t2])
    print(f"### Starting Research on: {TOPIC} ###")
    result = nchs_crew.kickoff()
    
    with open("Universal_Report.md", "w") as f:
        f.write(str(result))
    
    print("\n\nDone! Report saved to Universal_Report.md")