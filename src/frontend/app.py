import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="AI Engineer Sandbox", page_icon="🤖", layout="wide")

if "token" not in st.session_state:
    st.session_state.token = None

# Sidebar
with st.sidebar:
    st.header("🔐 Authentication (JWT/RLS)")
    if not st.session_state.token:
        with st.form("login_form"):
            st.write("Log in to isolate your data.")
            username = st.text_input("Username (e.g. bryan or company_x)")
            password = st.text_input("Password (password123)", type="password")
            submitted = st.form_submit_button("Log in")
            if submitted:
                res = requests.post(f"{API_URL}/auth/token", data={"username": username, "password": password})
                if res.status_code == 200:
                    st.session_state.token = res.json()["access_token"]
                    st.success("Logged in")
                    st.rerun()
                else:
                    st.error("Incorrect credentials")
    else:
        st.success("✅ You are securely logged in.")
        if st.button("Log out"):
            st.session_state.token = None
            st.rerun()

    st.markdown("---")
    st.header("📁 Multimodal Ingestion")
    
    uploaded_file = st.file_uploader(
        "Upload a file to your tenant", 
        type=["md", "txt", "pdf", "png", "jpg", "jpeg"]
    )
    
    if uploaded_file is not None and st.session_state.token:
        if st.button("Process file"):
            with st.spinner(f"Ingesting {uploaded_file.name}..."):
                try:
                    headers = {"Authorization": f"Bearer {st.session_state.token}"}
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    res = requests.post(f"{API_URL}/ingest/", headers=headers, files=files, timeout=120)
                    if res.status_code == 200:
                        stats = res.json()
                        st.success(f"✅ Done! {stats['inserted_chunks']} vectors generated and stored in your tenant.")
                    else:
                        st.error(f"API error: {res.json().get('detail', res.text)}")
                except Exception as e:
                    st.error(f"Error uploading file: {e}")
    elif uploaded_file is not None and not st.session_state.token:
        st.warning("⚠️ You must log in to upload files.")

st.title("🤖 Sandbox RAG Chat")
st.markdown("Multi-tenant RAG interface (JWT security and RLS in Postgres)")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sources" in message and message["sources"]:
            with st.expander("Sources"):
                for source in message["sources"]:
                    st.caption(f"- *{source['quote']}* (Doc ID: {source['document_id']})")
        if "confidence" in message:
            color = "green" if message["confidence"] > 0.8 else "orange"
            st.markdown(f"**Confidence:** :{color}[{message['confidence']}]")

if prompt := st.chat_input("Ask a question about the context..."):
    if not st.session_state.token:
        st.warning("⚠️ You must log in from the sidebar to chat.")
        st.stop()
        
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Thinking and routing..."):
            try:
                chat_history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
                payload = {"query": prompt, "history": chat_history}
                headers = {"Authorization": f"Bearer {st.session_state.token}"}
                
                response = requests.post(f"{API_URL}/chat/stream/", headers=headers, json=payload, stream=True, timeout=60)
                
                if response.status_code == 200:
                    sources_placeholder = st.empty()
                    confidence_placeholder = st.empty()
                    
                    final_sources = []
                    final_confidence = 0.0
                    
                    def stream_parser():
                        global final_sources, final_confidence
                        last_yielded_length = 0
                        for line in response.iter_lines():
                            if line:
                                decoded_line = line.decode('utf-8')
                                if decoded_line.startswith("data: "):
                                    json_str = decoded_line[6:]
                                    import json
                                    try:
                                        data = json.loads(json_str)
                                        if "error" in data:
                                            yield f"\n\n**Error:** {data['error']}"
                                            break
                                            
                                        current_answer = data.get("answer") or ""
                                        final_sources = data.get("sources") or []
                                        final_confidence = data.get("confidence_score") or 0.0
                                        
                                        if len(current_answer) > last_yielded_length:
                                            new_text = current_answer[last_yielded_length:]
                                            last_yielded_length = len(current_answer)
                                            yield new_text
                                    except json.JSONDecodeError:
                                        pass

                    final_answer = st.write_stream(stream_parser())
                    
                    if final_sources:
                        with sources_placeholder.expander("Sources"):
                            for source in final_sources:
                                st.caption(f"- *{source['quote']}* (Doc ID: {source['document_id']})")
                                
                    color = "green" if final_confidence > 0.8 else "orange"
                    confidence_placeholder.markdown(f"**Confidence:** :{color}[{final_confidence}]")
                    
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": final_answer,
                        "sources": final_sources,
                        "confidence": final_confidence
                    })
                    
                else:
                    st.error(f"API error: {response.status_code}")
            except Exception as e:
                st.error(f"Could not connect to the API at {API_URL}. Is FastAPI running? Error: {e}")
