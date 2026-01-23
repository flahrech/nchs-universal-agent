from crewai import Agent, Task, Crew
from langchain_community.tools.tavily_search import TavilySearchResults

# Initialize Search Tool
search_tool = TavilySearchResults(api_key="YOUR_TAVILY_KEY")

# Agent 1: The Industry Researcher
researcher = Agent(
  role='Healthcare Process Researcher',
  goal='Find cutting-edge Lean Six Sigma applications in top-tier hospitals',
  backstory='You are an expert in healthcare operational excellence at NCHS.',
  tools=[search_tool],
  verbose=True
)

# Agent 2: The Executive Writer
writer = Agent(
  role='Process Excellence Director',
  goal='Summarize research into a 1-page executive memo for NCHS leadership',
  backstory='You specialize in making complex data actionable for C-suite executives.',
  verbose=True
)