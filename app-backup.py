import streamlit as st
import os
import ssl
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai_tools import TavilySearchTool, YoutubeVideoSearchTool
from pptx import Presentation
from pptx.util import Inches, Pt

# --- 1. SYSTEM CONFIGURATION ---
load_dotenv()
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except:
    pass
os.environ["OTEL_SDK_DISABLED"] = "true"

# --- 2. TERMINAL-STYLE CALLBACK ---
class StreamlitCallbackHandler:
    def __init__(self, container):
        self.container = container

    def on_step(self, step):
        """Pipes agent terminal logs directly to the web UI."""
        with self.container:
            # Check if this is an Action (Agent thinking/using tool)
            if hasattr(step, 'tool'):
                st.markdown(f"**⚙️ TERMINAL > EXECUTING TOOL:** `{step.tool}`")
                # Using code block to mimic VS Code terminal look
                st.code(f"Thought: {getattr(step, 'thought', 'Analyzing...')}", language="text")
            
            # Check if this is a Result (Data coming back)
            elif hasattr(step, 'result'):
                with st.expander("📥 STDOUT > VIEW TOOL OUTPUT", expanded=False):
                    st.code(str(step.result), language="markdown")

# --- 3. PPT GENERATOR ---
def create_professional_ppt(ai_content, topic):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = topic.upper()
    slide.placeholders[1].text = "NCHS Executive Briefing"
    
    # Simple split by double newlines or headers for slides
    sections = str(ai_content).split('##')
    for section in sections:
        if len(section.strip()) < 10: continue
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        lines = section.strip().split('\n')
        slide.shapes.title.text = lines[0].replace('*', '').strip()
        body = "\n".join(lines[1:]).replace('*', '').strip()
        tf = slide.placeholders[1].text_frame
        tf.text = body
    
    path = "NCHS_Briefing.pptx"
    prs.save(path)
    return path

# --- 4. UI SETUP ---
st.set_page_config(page_title="NCHS Intelligence", page_icon="🧠", layout="wide")
st.title("🧠 NCHS Universal Intelligence Agent")

with st.sidebar:
    st.header("Research Parameters")
    research_topic = st.text_area("Objective", placeholder="e.g., Pediatric AI trends...")
    yt_url = st.text_input("YouTube Source (URL)")

# --- 5. EXECUTION ---
if st.button("🚀 Launch Research Mission"):
    if not research_topic:
        st.error("Please enter a research objective!")
    else:
        # Create a "Terminal" area for the live logs
        st.subheader("💻 Live Agent Terminal")
        terminal_container = st.container(border=True)
        handler = StreamlitCallbackHandler(terminal_container)

        with st.status("🤖 Agents are working...", expanded=True) as status:
            search_tool = TavilySearchTool()
            tools = [search_tool]
            if yt_url: tools.append(YoutubeVideoSearchTool(youtube_video_url=yt_url))

            researcher = Agent(
                role='Researcher', 
                goal=f'Research {research_topic}', 
                backstory='NCHS Analyst.', tools=tools, verbose=True
            )
            writer = Agent(
                role='Writer', 
                goal='Draft memo.', 
                backstory='NCHS Comms.', verbose=True
            )

            t1 = Task(description=f"Research {research_topic}.", agent=researcher, expected_output="Data.")
            t2 = Task(description=f"Draft memo. Use ## for headers.", agent=writer, context=[t1], expected_output="Clean memo.")

            crew = Crew(agents=[researcher, writer], tasks=[t1, t2], step_callback=handler.on_step)
            result = crew.kickoff()
            status.update(label="✅ Mission Complete", state="complete")

        # --- 6. TABS (Your preferred layout) ---
        st.divider()
        tab1, tab2 = st.tabs(["📝 Executive Summary", "🔍 Technical Logs"])

        with tab1:
            # Fixing formatting: Ensure markdown renders correctly
            st.markdown(result.raw) 
            
            ppt_path = create_professional_ppt(result.raw, research_topic)
            with open(ppt_path, "rb") as f:
                st.download_button("📂 Download PPT Briefing", f, file_name=ppt_path)

        with tab2:
            st.info("Full history of agent reasoning and tool outputs.")
            # Displaying the raw researcher output in a terminal-style code block
            st.code(result.tasks_output[0].raw, language="text")