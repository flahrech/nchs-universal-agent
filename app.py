import streamlit as st
import os
from crewai import Agent, Task, Crew
from crewai_tools import TavilySearchTool
from pptx import Presentation
from pptx.util import Pt

# --- 1. DATA: TOP 20 PEDIATRIC HOSPITALS (US News & World Report Style) ---
TOP_20_HOSPITALS = [
    "Cincinnati Children's", "Boston Children's", "CHOP", "Texas Children's", 
    "Children's Hospital Los Angeles", "Nationwide Children's", "Children's National",
    "UPMC Children's Pittsburgh", "Seattle Children's", "Johns Hopkins Children's",
    "Stanford Children's", "Colorado Children's", "Children's Healthcare of Atlanta",
    "Riley Children's", "St. Louis Children's", "Phoenix Children's",
    "Nicklaus Children's (NCHS)", "Primary Children's", "Duke Children's", "Ann & Robert H. Lurie"
]

STRATEGIC_FOCUS_AREAS = [
    "Clinical Excellence & Safety", "Operational Efficiency", 
    "Financial Sustainability", "Patient/Family Experience", 
    "Nursing Retention & Culture", "Digital Health & AI Integration"
]

# --- 2. THE TERMINAL LOG HANDLER ---
class StreamlitCallbackHandler:
    def __init__(self, container):
        self.container = container
    def on_step(self, step):
        with self.container:
            if hasattr(step, 'tool'):
                st.markdown(f"**⚙️ TERMINAL >** `{step.tool}`")
                st.code(f"Thought: {getattr(step, 'thought', 'Analyzing...')}", language="text")

# --- 3. UI SETUP ---
st.set_page_config(page_title="NCHS Benchmark Portal", layout="wide")
st.title("🏥 NCHS Strategic Benchmarking Portal")

with st.sidebar:
    st.header("1. Define Scope")
    research_topic = st.text_input("Primary Research Objective", "Pediatric Care Pathways")
    
    st.header("2. Select Peers to Benchmark")
    selected_hospitals = st.multiselect(
        "Select up to 5 Peer Institutions", 
        options=TOP_20_HOSPITALS,
        default=["CHOP", "Boston Children's"]
    )
    
    st.header("3. Strategic Focus")
    focus_area = st.selectbox("Focus Area", STRATEGIC_FOCUS_AREAS)
    
    st.divider()
    st.caption("Professional Plan Active | Always-On")

# --- 4. EXECUTION ---
if st.button("🚀 Run Comparative Analysis"):
    if not research_topic or not selected_hospitals:
        st.error("Please provide a topic and select at least one hospital.")
    else:
        peer_list = ", ".join(selected_hospitals)
        
        # UI Setup for Logs
        st.subheader("💻 Live Analysis Stream")
        terminal_container = st.container(border=True)
        handler = StreamlitCallbackHandler(terminal_container)

        with st.status("🤖 AI Research Team Assembling...", expanded=True) as status:
            researcher = Agent(
                role='Comparative Analyst',
                goal=f'Compare {research_topic} across {peer_list} with a focus on {focus_area}.',
                backstory='Specialist in hospital quality data and market intelligence.',
                tools=[TavilySearchTool()], verbose=True
            )
            
            writer = Agent(
                role='Executive Strategist',
                goal='Draft a board-ready comparative briefing.',
                backstory='NCHS Strategic Communications expert.',
                verbose=True
            )

            t1 = Task(
                description=f"Analyze {research_topic} at {peer_list}. Specifically look for data related to {focus_area}.",
                agent=researcher,
                expected_output="A structured comparison of peer initiatives."
            )
            
            t2 = Task(
                description=f"Create a memo comparing NCHS to {peer_list} regarding {research_topic}. Use '##' for slide headers.",
                agent=writer,
                context=[t1],
                expected_output="Final strategic memo."
            )

            crew = Crew(agents=[researcher, writer], tasks=[t1, t2], step_callback=handler.on_step)
            result = crew.kickoff()
            status.update(label="✅ Analysis Complete", state="complete")

        # --- 5. TABS ---
        tab1, tab2 = st.tabs(["📝 Strategic Memo", "🔍 Raw Peer Data"])
        with tab1:
            st.markdown(result.raw)
        with tab2:
            st.code(result.tasks_output[0].raw)