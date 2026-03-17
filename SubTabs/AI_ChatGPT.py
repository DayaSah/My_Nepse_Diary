import streamlit as st
from openai import OpenAI

def render(role, db_context):
    st.subheader("🟢 ChatGPT Analyst")
    st.markdown("Powered by OpenAI's `gpt-4o-mini`. Industry standard for logical deduction and formatting.")

    try:
        client = OpenAI(api_key=st.secrets["openai"]["api_key"])
    except Exception as e:
        st.warning("OpenAI API Key missing or invalid. Please check your secrets.toml.")
        return

    user_query = st.text_area("Ask ChatGPT about your portfolio:", key="gpt_query")
    
    if st.button("🚀 Ask ChatGPT", type="primary"):
        if user_query:
            with st.spinner("ChatGPT is analyzing..."):
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": db_context},
                            {"role": "user", "content": user_query}
                        ]
                    )
                    st.divider()
                    st.markdown("### 💡 Analysis")
                    st.write(response.choices[0].message.content)
                except Exception as e:
                    st.error(f"API Error: {e}")
        else:
            st.warning("Please enter a question.")
