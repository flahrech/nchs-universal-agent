import streamlit as st
import os
import ssl
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai_tools import TavilySearchTool, YoutubeVideoSearchTool
from pptx import Presentation

# --- 1. SYSTEM CONFIGURATION ---
load_dotenv()

# Bypass SSL for NCHS Firewall
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

os.environ["OTEL_SDK_DISABLED"] = "true"

# --- 2. PAGE SETUP ---
st.set_page_config(page_title="NCHS Universal Agent", page_icon="🧠", layout="wide")
st.title("🧠 NCHS Universal Intelligence Agent")
st.markdown("### Strategic Research & Executive Analysis Portal")

# --- 3. SIDEBAR: DYNAMIC INPUTS ---
with st.sidebar:
    st.header("Research Parameters")
    
    # MASTER TOPIC INPUT
    research_topic = st.text_area(
        "What is your research objective?", 
        placeholder="e.g., Impact of AI on pediatric radiology costs, or trends in ER nurse retention...",
        height=150
    )
    
    target_hospital = st.text_input("Benchmark Peers", value="CHOP, Boston Children's")
    
    st.divider()
    st.header("Multimedia Intelligence")
    yt_url = st.text_input("YouTube Expert Source (URL)", placeholder="https://youtube.com/watch?v=...")
    
    st.divider()
    st.caption("v2.0 Universal Edition - NCHS Innovation")

# --- 4. POWERPOINT GENERATOR ---
def create_universal_report(ai_content):
    try:
        prs = Presentation('NCHS_Template.pptx')
    except:
        prs = Presentation()
    
    sections = str(ai_content).split('##')
    for section in sections:
        section_text = str(section).strip()
        if len(section_text) > 20:
            slide_layout = prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0]
            slide = prs.slides.add_slide(slide_layout)
            lines = section_text.split('\n')
            slide.shapes.title.text = lines[0].replace('#', '').strip()
            body_text = "\n".join(lines[1:]).strip()
            if slide.placeholders:
                try: slide.placeholders[1].text = body_text
                except: pass
    
    path = "NCHS_Strategic_Briefing.pptx"
    prs.save(path)
    return path

# --- 5. MAIN EXECUTION ---
if st.button("🚀 Launch Research Mission"):
    if not research_topic:
        st.error("Please enter a research objective first!")
    else:
        # Initialize Tools
        search_tool = TavilySearchTool()
        tools = [search_tool]
        if yt_url:
            tools.append(YoutubeVideoSearchTool(youtube_video_url=yt_url))

        with st.status("🤖 Digital Department is working...", expanded=True) as status:
            
            # AGENTS
            researcher = Agent(
                role='Lead Strategic Researcher',
                goal=f'Conduct deep-dive research on: {research_topic}',
                backstory='Expert analyst at Nicklaus Children\'s. You specialize in synthesizing complex healthcare trends.',
                tools=tools,
                verbose=True
            )

            writer = Agent(
                role='Executive Communications Director',
                goal='Translate technical research into a board-ready executive briefing.',
                backstory='Specialist in NCHS leadership communications and strategic storytelling.',
                verbose=True
            )

            # DYNAMIC TASKS
            task1 = Task(
                description=f"Investigate {research_topic} with a focus on benchmarks from {target_hospital}. "
                            f"Include any specific data points or expert quotes found in the provided YouTube source.",
                expected_output="A structured research report with clinical, financial, and operational insights.",
                agent=researcher
            )

            task2 = Task(
                description=f"Synthesize the findings about {research_topic} into an Executive Memo. "
                            "Use '##' headers for: Executive Summary, Market Analysis, and Recommendations.",
                expected_output="A formatted markdown memo for board presentation.",
                agent=writer,
                context=[task1]
            )

            # THE CREW
            crew = Crew(agents=[researcher, writer], tasks=[task1, task2], process=Process.sequential)
            result = crew.kickoff()
            status.update(label="✅ Mission Accomplished!", state="complete", expanded=False)

        # RESULTS DISPLAY
        st.subheader("Executive Strategic Memo")
        st.markdown(result)

        ppt_path = create_universal_report(result)
        with open(ppt_path, "rb") as f:
            st.download_button("📂 Download PowerPoint Briefing", f, file_name=ppt_path)