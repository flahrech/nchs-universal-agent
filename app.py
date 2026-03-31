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
if "dynamic_followups" not in st.session_state:
    st.session_state.dynamic_followups = []

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
            st.session_state.dynamic_followups = []
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

# --- 7. DYNAMIC FOLLOW-UP GENERATOR ---
def generate_followup_questions(topic, focus, peer_list, memo_snippet):
    """Generate 6 follow-up questions tightly scoped to the research topic."""
    followup_agent = Agent(
        role='Research Scoping Assistant',
        goal=f'Generate 6 sharp follow-up questions strictly about: {topic}',
        backstory=(
            f'You are a strategic research assistant helping NCHS leadership go deeper on a specific topic. '
            f'The topic is: "{topic}". The strategic focus is: "{focus}". '
            f'Peers analyzed: {peer_list}. '
            f'You generate follow-up questions that are 100% scoped to this topic — '
            f'never generic hospital questions unless they directly relate to {topic}. '
            f'Here is a snippet of the analysis already completed:\n{memo_snippet[:800]}'
        ),
        tools=[],
        verbose=False
    )

    followup_task = Task(
        description=(
            f'Generate exactly 6 follow-up questions for NCHS leadership to explore further about "{topic}" '
            f'in the context of {focus} across peers: {peer_list}.\n\n'
            f'Rules:\n'
            f'- Every question must be directly and specifically about "{topic}"\n'
            f'- Questions should dig deeper into what was already researched\n'
            f'- Do NOT ask generic hospital questions unrelated to "{topic}"\n'
            f'- Questions should be actionable and strategic for NCHS\n'
            f'- Mix of: deeper data requests, competitive comparisons, implementation asks, gap analyses\n\n'
            f'Return ONLY a plain numbered list 1-6, one question per line, no headers, no explanation.'
        ),
        agent=followup_agent,
        expected_output="A numbered list of exactly 6 follow-up questions scoped to the research topic."
    )

    crew = Crew(
        agents=[followup_agent],
        tasks=[followup_task],
        process=Process.sequential
    )

    result = crew.kickoff()
    
    # Parse the numbered list into a clean Python list
    lines = result.raw.strip().split("\n")
    questions = []
    for line in lines:
        line = line.strip()
        if line and len(line) > 10:
            # Strip leading numbers like "1." or "1)"
            import re
            cleaned = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            if cleaned:
                questions.append(cleaned)
    return questions[:6]

# --- 8. FOLLOW-UP AGENT ---
def run_followup(user_question):
    context = f"""
You are an expert healthcare strategist for Nicklaus Children's Hospital (NCHS).
You have just completed a benchmarking analysis on the topic: "{st.session_state.last_topic}".

Here is the full executive memo:
{st.session_state.last_result_raw}

Here is the raw peer research data:
{st.session_state.last_peer_data}

Peers analyzed: {st.session_state.last_peer_list}
Strategic Focus: {st.session_state.last_focus}

Chat history so far:
{chr(10).join([f"{m['role'].upper()}: {m['content']}" for m in st.session_state.chat_history[-6:]])}

IMPORTANT: Keep your answer tightly scoped to "{st.session_state.last_topic}". 
Do not introduce unrelated hospital metrics unless they directly support answering this question.
Be direct, strategic, and board-ready.
"""
    followup_agent = Agent(
        role='NCHS Strategic Advisor',
        goal=f'Answer this follow-up question about "{st.session_state.last_topic}": {user_question}',
        backstory=context,
        tools=[TavilySearchTool()],
        verbose=True,
        memory=True
    )

    followup_task = Task(
        description=(
            f'Answer this follow-up question:\n\n"{user_question}"\n\n'
            f'CRITICAL RULES:\n'
            f'- Stay strictly scoped to the topic: "{st.session_state.last_topic}"\n'
            f'- Only include financial data, rankings, or other metrics if they are DIRECTLY relevant to answering this question about "{st.session_state.last_topic}"\n'
            f'- Include specific data points, percentages, or stats where available\n'
            f'- Reference specific peer hospitals by name\n'
            f'- Provide 2-3 actionable recommendations for NCHS scoped to "{st.session_state.last_topic}"\n'
            f'- Format with clear ## headers\n'
            f'- NEVER write "[As above]" or any placeholder — always write the full response'
        ),
        agent=followup_agent,
        expected_output=(
            f'A complete, topic-focused response about "{st.session_state.last_topic}" '
            f'with data, peer comparisons, and NCHS recommendations. No placeholders.'
        )
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

# --- 9. MAIN ANALYSIS ---
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
                role='Focused Research Analyst',
                goal=f'Research "{research_topic}" across {peer_list} through the lens of {focus_area}.',
                backstory=(
                    f'You are a senior healthcare intelligence analyst. Your ONLY job in this analysis is to '
                    f'research "{research_topic}" — that is the primary objective and everything must serve it. '
                    f'You surface data, programs, outcomes, and innovations specifically related to "{research_topic}". '
                    f'You do NOT default to generic hospital metrics like revenue, US News rankings, or bed counts '
                    f'UNLESS they are directly and specifically relevant to "{research_topic}". '
                    f'Every finding must connect back to the research objective. '
                    + (f'Context from prior session analyses:\n{memory_context}' if memory_context else '')
                ),
                tools=[TavilySearchTool()],
                verbose=True,
                memory=True
            )

            writer = Agent(
                role='Executive Strategist & Communications Director',
                goal=f'Write a focused executive memo about "{research_topic}" — nothing more, nothing less.',
                backstory=(
                    f'You are NCHS\'s strategic communications officer. You are writing a memo specifically about '
                    f'"{research_topic}". Every section must serve this topic. '
                    f'Do NOT include generic hospital benchmarking data (financials, rankings, bed counts) '
                    f'unless it directly and materially relates to "{research_topic}". '
                    f'If a data point does not help the reader understand "{research_topic}" better, leave it out. '
                    f'You NEVER use placeholders like "[As above]" — every section is fully written. '
                    f'You always cite specific numbers and name specific peer institutions. '
                    + (f'Build on prior analyses where relevant:\n{memory_context}' if memory_context else '')
                ),
                verbose=True,
                memory=True
            )

            t1 = Task(
                description=(
                    f'Research "{research_topic}" across these peer institutions: {peer_list}.\n\n'
                    f'Strategic Focus: {focus_area}\n\n'
                    f'YOUR PRIMARY DIRECTIVE: Everything you find must be about "{research_topic}".\n\n'
                    f'For each peer institution, find:\n'
                    f'1. Specific programs, initiatives, or models related to "{research_topic}"\n'
                    f'2. Measurable outcomes and results tied to "{research_topic}" (stats, rates, scores)\n'
                    f'3. Innovations or investments specifically in "{research_topic}"\n'
                    f'4. What is working well and what gaps exist in "{research_topic}" at each peer\n'
                    f'5. Any financial, operational, or quality data ONLY IF it directly measures "{research_topic}"\n\n'
                    f'DO NOT include: general hospital revenue, US News rankings, bed counts, or any data '
                    f'that does not specifically measure or relate to "{research_topic}".\n\n'
                    f'Be specific. Use real numbers. Avoid generic statements.\n'
                    + (f'Prior context:\n{memory_context}' if memory_context else '')
                ),
                agent=researcher,
                expected_output=(
                    f'A focused, data-rich research report about "{research_topic}" across all peer institutions. '
                    f'All findings directly tied to the research topic. No generic hospital metrics.'
                )
            )

            t2 = Task(
                description=(
                    f'Using ONLY the research provided, write a COMPLETE Executive Strategic Memo for NCHS '
                    f'leadership focused entirely on "{research_topic}".\n\n'
                    f'CRITICAL RULES:\n'
                    f'- The memo is about "{research_topic}" — every section must serve this topic\n'
                    f'- Do NOT include financial benchmarks, US News rankings, bed counts, or general hospital '
                    f'metrics UNLESS they directly measure or explain "{research_topic}"\n'
                    f'- NEVER write "[As above]", "[See above]", or any placeholder\n'
                    f'- Every section must be fully written with complete sentences and specific data\n\n'
                    f'Topic: {research_topic} | Focus: {focus_area} | Peers: {peer_list}\n\n'
                    f'Write ALL of these sections IN FULL using ## headers:\n\n'
                    f'## Executive Summary\n'
                    f'3-4 sentences summarizing the most critical findings about "{research_topic}" across peers.\n\n'
                    f'## What Peers Are Doing: {research_topic}\n'
                    f'A detailed breakdown of each peer\'s specific programs, models, and initiatives '
                    f'related to "{research_topic}". Include a comparison table where useful.\n\n'
                    f'## Performance & Outcomes Data\n'
                    f'Specific metrics, rates, scores, and results that measure "{research_topic}" performance. '
                    f'Only include data that directly reflects "{research_topic}".\n\n'
                    f'## Innovations & Investments in {research_topic}\n'
                    f'What are peers investing in or piloting that advances "{research_topic}"? '
                    f'Include programs, partnerships, technologies, and dollar amounts where known.\n\n'
                    f'## Where NCHS Stands: Gaps & Advantages\n'
                    f'Specifically where NCHS leads and lags peers on "{research_topic}". Be direct.\n\n'
                    f'## Strategic Recommendations for NCHS\n'
                    f'5 fully explained recommendations, each directly tied to improving "{research_topic}" at NCHS. '
                    f'Include: the action, the peer evidence supporting it, and the expected impact.\n\n'
                    f'## Key Data Points at a Glance\n'
                    f'8-10 bullet points of the most important stats and findings about "{research_topic}".\n\n'
                    f'Write for a C-suite audience. Every number and claim must relate to "{research_topic}".'
                    + (f'\n\nPrior context:\n{memory_context}' if memory_context else '')
                ),
                agent=writer,
                context=[t1],
                expected_output=(
                    f'A complete, fully written executive memo focused entirely on "{research_topic}". '
                    f'All 7 sections fully populated. No generic hospital data. No placeholders.'
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

        # Generate dynamic follow-up questions scoped to this topic
        with st.spinner("💡 Generating follow-up questions..."):
            st.session_state.dynamic_followups = generate_followup_questions(
                research_topic, focus_area, peer_list, result.raw
            )

# --- 10. RESULTS + CHAT ---
if st.session_state.analysis_done:
    tab1, tab2, tab3 = st.tabs(["📝 Executive Memo", "🔍 Raw Peer Data", "💬 Follow-Up Chat"])

    with tab1:
        if "[As above]" in st.session_state.last_result_raw or len(st.session_state.last_result_raw) < 200:
            st.warning("⚠️ The memo output appears incomplete. Try running the analysis again.")
        st.markdown(st.session_state.last_result_raw)

    with tab2:
        st.code(st.session_state.last_peer_data)

    with tab3:
        st.subheader(f"💬 Go Deeper on: {st.session_state.last_topic}")
        st.caption("All questions and responses are scoped to your research objective.")

        if st.session_state.dynamic_followups:
            st.markdown("**💡 Suggested Questions:**")
            cols = st.columns(2)
            for i, suggestion in enumerate(st.session_state.dynamic_followups):
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

        if prompt := st.chat_input(f"Ask a follow-up question about {st.session_state.last_topic}..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("🤖 Researching your question..."):
                    response = run_followup(prompt)
                st.markdown(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.rerun()