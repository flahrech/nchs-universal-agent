import streamlit as st
import os
from crewai import Agent, Task, Crew, Process
from crewai_tools import TavilySearchTool
from pptx import Presentation
from pptx.util import Pt

# --- 1. DATA ---
TOP_20_HOSPITALS = [
    "Cincinnati Children's", "Boston Children's", "CHOP", "Texas Children's", 
    "Children's Hospital Los Angeles", "Nationwide Children's", "Children's National",
    "UPMC Children's Pittsburgh", "Seattle Children's", "Johns Hopkins Children's",
    "Stanford Children's", "Colorado Children's", "Children's Healthcare of Atlanta",
    "Riley Children's", "St. Louis Children's", "Phoenix Children's",
    "Nicklaus Children's (NCHS)", "Primary Children's", "Duke Children's", "Ann & Robert H. Lurie",
    "Joe DiMaggio Children's Hospital", "Broward Health"
]

STRATEGIC_FOCUS_AREAS = [
    "Clinical Excellence & Safety", "Operational Efficiency", 
    "Financial Sustainability", "Patient/Family Experience", 
    "Nursing Retention & Culture", "Digital Health & AI Integration",
    "Quality Management", "Strategy", "Research"
]

SUGGESTED_FOLLOWUPS = [
    "What are the top 3 gaps NCHS should close in the next 12 months?",
    "Which peer hospital has the strongest financial performance? Show data.",
    "What nursing retention strategies are peers using that NCHS could adopt?",
    "Summarize any AI or digital health investments made by these peers.",
    "What quality metrics (e.g. HCAHPS, readmission rates) distinguish top performers?",
    "Build a SWOT analysis for NCHS based on this benchmarking data.",
    "What research programs or grants do these peers have that NCHS lacks?",
    "Which hospital has the best patient experience scores and what drives it?"
]

# --- 2. TERMINAL LOG HANDLER ---
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

# --- 4. SESSION STATE ---
if "analysis_history" not in st.session_state:
    st.session_state.analysis_history = []
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
if "last_result_raw" not in st.session_state:
    st.session_state.last_result_raw = ""
if "last_peer_data" not in st.session_state:
    st.session_state.last_peer_data = ""
if "last_peer_list" not in st.session_state:
    st.session_state.last_peer_list = ""
if "last_focus" not in st.session_state:
    st.session_state.last_focus = ""
if "last_topic" not in st.session_state:
    st.session_state.last_topic = ""

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("1. Define Scope")
    research_topic = st.text_input("Primary Research Objective", "Pediatric Care Pathways")
    
    st.header("2. Select Peers to Benchmark")
    select_all = st.checkbox("Select All Institutions")
    selected_hospitals = st.multiselect(
        "Select Peer Institutions", 
        options=TOP_20_HOSPITALS,
        default=TOP_20_HOSPITALS if select_all else ["CHOP", "Boston Children's"]
    )
    
    st.header("3. Strategic Focus")
    focus_area = st.selectbox("Focus Area", STRATEGIC_FOCUS_AREAS)

    st.divider()
    st.header("🧠 Session Memory")
    if st.session_state.analysis_history:
        st.caption(f"{len(st.session_state.analysis_history)} prior analysis run(s) in memory")
        for i, entry in enumerate(st.session_state.analysis_history):
            with st.expander(f"Run {i+1}: {entry['topic']} — {entry['focus']}"):
                st.write(f"**Peers:** {entry['hospitals']}")
                st.write(f"**Summary:** {entry['summary']}")
        if st.button("🗑️ Clear Memory"):
            st.session_state.analysis_history = []
            st.session_state.chat_history = []
            st.session_state.analysis_done = False
            st.session_state.last_result_raw = ""
            st.session_state.last_peer_data = ""
            st.rerun()
    else:
        st.caption("No prior runs yet. Memory builds as you run analyses.")

    st.divider()
    st.caption("Professional Plan Active | Always-On")

# --- 6. MEMORY CONTEXT BUILDER ---
def build_memory_context():
    if not st.session_state.analysis_history:
        return ""
    lines = ["### Prior Analyses (Session Memory):"]
    for i, entry in enumerate(st.session_state.analysis_history):
        lines.append(
            f"- Run {i+1}: Topic='{entry['topic']}', Focus='{entry['focus']}', "
            f"Peers={entry['hospitals']}. Summary: {entry['summary']}"
        )
    return "\n".join(lines)

# --- 7. FOLLOW-UP AGENT ---
def run_followup(user_question):
    context = f"""
You are an expert healthcare strategist for Nicklaus Children's Hospital (NCHS).
You have just completed a benchmarking analysis. Here is the full executive memo:

{st.session_state.last_result_raw}

Here is the raw peer research data:

{st.session_state.last_peer_data}

Topic: {st.session_state.last_topic}
Peers analyzed: {st.session_state.last_peer_list}
Strategic Focus: {st.session_state.last_focus}

Chat history so far:
{chr(10).join([f"{m['role'].upper()}: {m['content']}" for m in st.session_state.chat_history[-6:]])}

Now answer the following follow-up question with specificity, citing data and stats where possible. 
Be direct, strategic, and board-ready in your response.
"""
    followup_agent = Agent(
        role='NCHS Strategic Advisor',
        goal=f'Answer follow-up question with data-backed insights: {user_question}',
        backstory=context,
        tools=[TavilySearchTool()],
        verbose=True,
        memory=True
    )

    followup_task = Task(
        description=(
            f"Answer this question using all available benchmarking context and supplemental web research if needed:\n\n"
            f"'{user_question}'\n\n"
            f"Your response must:\n"
            f"- Include specific data points, percentages, financials, or stats where available\n"
            f"- Reference specific peer hospitals by name\n"
            f"- Provide 2-3 actionable recommendations for NCHS\n"
            f"- Be formatted with clear headers using ##\n"
            f"- NEVER write '[As above]' or any placeholder — always write the full response"
        ),
        agent=followup_agent,
        expected_output="A complete, data-rich, board-ready strategic response with headers and recommendations. No placeholders."
    )

    followup_crew = Crew(
        agents=[followup_agent],
        tasks=[followup_task],
        process=Process.sequential,
        memory=True,
        embedder={
            "provider": "openai",
            "config": {"model": "text-embedding-3-small"}
        }
    )

    result = followup_crew.kickoff()
    return result.raw

# --- 8. MAIN ANALYSIS ---
if st.button("🚀 Run Comparative Analysis"):
    if not research_topic or not selected_hospitals:
        st.error("Please provide a topic and select at least one hospital.")
    else:
        peer_list = ", ".join(selected_hospitals)
        memory_context = build_memory_context()

        st.subheader("💻 Live Analysis Stream")
        terminal_container = st.container(border=True)
        handler = StreamlitCallbackHandler(terminal_container)

        with st.status("🤖 AI Research Team Assembling...", expanded=True) as status:

            researcher = Agent(
                role='Comparative Intelligence Analyst',
                goal=f'Deeply research {research_topic} across {peer_list} with focus on {focus_area}.',
                backstory=(
                    'You are a senior healthcare intelligence analyst specializing in pediatric hospital benchmarking. '
                    'You are known for surfacing hard numbers: revenue figures, bed counts, staffing ratios, quality scores, '
                    'grant funding, readmission rates, HCAHPS scores, operating margins, and technology investments. '
                    'Never give vague summaries — always anchor findings in real data and statistics. '
                    + (f'Context from prior session analyses:\n{memory_context}' if memory_context else '')
                ),
                tools=[TavilySearchTool()],
                verbose=True,
                memory=True
            )

            writer = Agent(
                role='Executive Strategist & Communications Director',
                goal='Draft a data-rich, board-ready executive memo with financials, stats, and strategic recommendations.',
                backstory=(
                    'You are NCHS\'s top strategic communications officer. You translate raw research into '
                    'compelling, data-forward executive memos that CEOs and boards act on. '
                    'Your memos always include: key statistics, financial comparisons, performance benchmarks, '
                    'competitive gaps, and 3-5 prioritized strategic recommendations. '
                    'You use tables where helpful and always cite specific numbers. '
                    'IMPORTANT: You ALWAYS write the full memo content. You NEVER use placeholders like '
                    '"[As above]", "[See above]", "[Insert data]", or any similar shorthand. '
                    'Every section must be fully written out with complete sentences and real data. '
                    + (f'Build on prior analyses where relevant:\n{memory_context}' if memory_context else '')
                ),
                verbose=True,
                memory=True
            )

            t1 = Task(
                description=(
                    f"Conduct a comprehensive benchmark analysis of '{research_topic}' across these peer institutions: {peer_list}.\n\n"
                    f"Strategic Focus Area: {focus_area}\n\n"
                    f"Your research MUST include for each hospital where available:\n"
                    f"1. **Financial data**: annual revenue, operating margin, recent capital investments\n"
                    f"2. **Clinical metrics**: readmission rates, mortality indices, HCAHPS scores, safety grades\n"
                    f"3. **Operational stats**: bed capacity, patient volume, average length of stay, staff-to-patient ratios\n"
                    f"4. **Strategic initiatives**: major programs, technology investments, AI/digital health pilots\n"
                    f"5. **Research & grants**: NIH funding, active clinical trials, research output\n"
                    f"6. **Workforce**: nursing turnover rates, Magnet status, recruitment programs\n"
                    f"7. **Rankings & recognition**: US News rankings, Leapfrog scores, accreditations\n\n"
                    f"Be specific. Use real numbers. Avoid generic statements. "
                    f"Do NOT use placeholders — write all findings in full.\n"
                    + (f"Prior context to build upon:\n{memory_context}" if memory_context else "")
                ),
                agent=researcher,
                expected_output=(
                    "A detailed, data-rich comparison matrix covering financials, clinical metrics, operations, "
                    "strategic initiatives, and rankings for each peer institution. All sections fully written, no placeholders."
                )
            )

            t2 = Task(
                description=(
                    f"Using ONLY the research data provided to you in context from the researcher, "
                    f"write a COMPLETE, FULLY WRITTEN board-ready Executive Strategic Memo for NCHS leadership.\n\n"
                    f"CRITICAL RULES:\n"
                    f"- NEVER write '[As above]', '[See above]', '[Insert]', or ANY placeholder text\n"
                    f"- NEVER reference a previous section with shorthand — always restate and expand the data\n"
                    f"- Every section must be fully written with complete sentences, real numbers, and specific insights\n"
                    f"- If a data point was mentioned in the research, include it explicitly in the relevant section\n\n"
                    f"Topic: {research_topic} | Focus: {focus_area} | Peers: {peer_list}\n\n"
                    f"Write every one of these sections IN FULL using '##' headers:\n\n"
                    f"## Executive Summary\n"
                    f"3-4 sentence high-impact overview with the most critical numbers and findings.\n\n"
                    f"## Peer Performance Snapshot\n"
                    f"A comparative breakdown showing key metrics side-by-side for each peer institution. "
                    f"Include a markdown table where possible.\n\n"
                    f"## Financial Benchmarks\n"
                    f"Write out revenue figures, operating margins, and capital investments for each peer. "
                    f"Explicitly compare to NCHS where data is available.\n\n"
                    f"## Clinical Quality & Safety Metrics\n"
                    f"Write out readmission rates, safety grades, HCAHPS scores, mortality indices, and rankings "
                    f"for each peer. Identify top and bottom performers.\n\n"
                    f"## Strategic Initiatives & Innovation\n"
                    f"Detail what each peer is investing in — AI programs, digital health, care pathway redesigns, "
                    f"research expansions. Be specific about programs and dollar amounts where known.\n\n"
                    f"## Competitive Gaps & Opportunities\n"
                    f"Explicitly state where NCHS is behind peers and where NCHS leads. Use specific metrics.\n\n"
                    f"## Strategic Recommendations for NCHS\n"
                    f"Write 5 fully explained, prioritized recommendations. Each must include: the action, "
                    f"the rationale based on peer data, and the expected impact.\n\n"
                    f"## Key Data Points at a Glance\n"
                    f"8-10 bullet points of the most important statistics and findings from this entire analysis.\n\n"
                    f"Write for a C-suite audience. Use real numbers throughout."
                    + (f"\n\nReference and build upon prior analyses where relevant:\n{memory_context}" if memory_context else "")
                ),
                agent=writer,
                context=[t1],
                expected_output=(
                    "A complete, fully written executive memo with all 8 sections populated with real data, "
                    "financial comparisons, clinical benchmarks, competitive analysis, and 5 strategic recommendations. "
                    "Zero placeholders. Formatted for board presentation."
                )
            )

            crew = Crew(
                agents=[researcher, writer],
                tasks=[t1, t2],
                process=Process.sequential,
                memory=True,
                embedder={
                    "provider": "openai",
                    "config": {"model": "text-embedding-3-small"}
                },
                output_log_file="nchs_crew_log.txt",
                step_callback=handler.on_step
            )

            result = crew.kickoff()
            status.update(label="✅ Analysis Complete", state="complete")

        # Save to session state
        st.session_state.last_result_raw = result.raw
        st.session_state.last_peer_data = result.tasks_output[0].raw
        st.session_state.last_peer_list = peer_list
        st.session_state.last_focus = focus_area
        st.session_state.last_topic = research_topic
        st.session_state.analysis_done = True
        st.session_state.chat_history = []

        summary_snippet = result.raw[:300].replace("\n", " ") + "..." if len(result.raw) > 300 else result.raw
        st.session_state.analysis_history.append({
            "topic": research_topic,
            "focus": focus_area,
            "hospitals": peer_list,
            "summary": summary_snippet
        })

# --- 9. RESULTS + CHAT ---
if st.session_state.analysis_done:
    tab1, tab2, tab3 = st.tabs(["📝 Executive Memo", "🔍 Raw Peer Data", "💬 Follow-Up Chat"])

    with tab1:
        # Guard against placeholder output — show warning if detected
        if "[As above]" in st.session_state.last_result_raw or len(st.session_state.last_result_raw) < 200:
            st.warning("⚠️ The memo output appears incomplete. Try running the analysis again.")
        st.markdown(st.session_state.last_result_raw)

    with tab2:
        st.code(st.session_state.last_peer_data)

    with tab3:
        st.subheader("💬 Continue the Analysis")
        st.caption("Ask follow-up questions, request deeper dives, or explore specific data points.")

        st.markdown("**💡 Suggested Questions:**")
        cols = st.columns(2)
        for i, suggestion in enumerate(SUGGESTED_FOLLOWUPS):
            with cols[i % 2]:
                if st.button(suggestion, key=f"suggestion_{i}"):
                    st.session_state.chat_history.append({"role": "user", "content": suggestion})
                    with st.spinner("🤖 Researching..."):
                        response = run_followup(suggestion)
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    st.rerun()

        st.divider()

        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input("Ask a follow-up question about the benchmarking analysis..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("🤖 Researching your question..."):
                    response = run_followup(prompt)
                st.markdown(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.rerun()