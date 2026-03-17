import streamlit as st
import google.generativeai as genai

def render(role, db_context):
    st.subheader("🔵 Gemini 2.0 Analyst")
    st.markdown("Powered by Google's `gemini-2.5-flash` model. Excellent at fast, broad quantitative reasoning.")

    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        st.warning("Gemini API Key missing or invalid. Please check your secrets.toml.")
        return

    user_query = st.text_area("Ask Gemini about your portfolio:", key="gemini_query")
    
    if st.button("🚀 Ask Gemini", type="primary"):
        if user_query:
            with st.spinner("Gemini is analyzing..."):
                try:
                    full_prompt = f"{db_context}\n\nUser Query: {user_query}"
                    response = model.generate_content(full_prompt)
                    st.divider()
                    st.markdown("### 💡 Analysis")
                    st.write(response.text)
                except Exception as e:
                    st.error(f"API Error: {e}")
        else:
            st.warning("Please enter a question.")
