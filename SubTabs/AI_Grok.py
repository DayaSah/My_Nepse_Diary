import streamlit as st
from openai import OpenAI

def render(role, db_context):
    st.subheader("✖️ Grok Analyst")
    st.markdown("Powered by xAI's `grok-beta`. Known for uncensored, highly direct market sentiment analysis.")

    try:
        # We use the OpenAI client, but point it at xAI's servers!
        client = OpenAI(
            api_key=st.secrets["xai"]["api_key"],
            base_url="https://api.x.ai/v1",
        )
    except Exception as e:
        st.warning("xAI API Key missing or invalid. Please check your secrets.toml.")
        return

    user_query = st.text_area("Ask Grok about your portfolio:", key="grok_query")
    
    if st.button("🚀 Ask Grok", type="primary"):
        if user_query:
            with st.spinner("Grok is analyzing..."):
                try:
                    response = client.chat.completions.create(
                        model="grok-beta",
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
