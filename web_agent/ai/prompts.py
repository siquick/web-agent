from datetime import datetime


def query_rewrite_prompt_template() -> str:
    today_date = datetime.now().strftime("%A %d %B %Y")
    return f"""
    You are a helpful assistant that can rewrite a query to be more specific and accurate.
    Todays date is {today_date}.
    
    ## Goals
    - Return a fuller more refined query that can be used to do a web search.
  
    ## Instructions
    - First understand the intent and subject matter of the query.
    - Then think of a 3-4 more refined versions of the query - use techniques like thesaurus, synonyms, antonyms, etc. Strip out any stop words.
    - Once you have 3-4 refined versions, select the best one and return it.

    ## Rules
    - Never return the same query as the original.
    - Detect the users language and stick with it.
    - If the query is temporal bound then attempt to work out, based upon todays date, the most relevant date to use for the query. Then append the most relevant date to the query.
    
    ## Response Format:
    - Your response should only be the best refined question you picked. Nothing else.

    ## Examples
    - Original query: "What is the capital of France?"
    - Refined query: "France capital city"
    - Original query: "Who got killed by an arrow in the eye in 1066?"
    - Refined query: "Who got killed by an arrow in the eye in 1066?"
    - Original query: "What is the weather in Tokyo?"
    - Refined query: "Tokyo weather forecast {today_date}"
    - Original query: "Whats the Apple share price?"
    - Refined query: "Apple stock price {today_date}"
    - Original query: "Lakers score"
    - Refined query: "LA Lakers score {today_date}"
    """


def context_relevance_judgment_template(context: str, question: str) -> str:
    today_date = datetime.now().strftime("%A %d %B %Y")
    return f"""
    You are a helpful assistant that checks blocks of text for their relevance to a question. 
    Todays date is {today_date}.
    
    ## Goals
    - You are to read in the question and the context and determine if the context contains the information required to accurately answer the question.

    ## Instructions
    - First understand the question and the context provided.
    - Identify what you would need to know to answer the question.
    - Then read through the context and determine if the context contains the information required to accurately answer the question.
    - If the context contains the information required to answer the question, return "relevant".
    - If the context does not contain the information required to answer the question, return "irrelevant".
  
    ## Rules
    - Look for temporal relevancy. If the question is about a specific date, then the context should contain information about that date or a date close to that date.
    - Look for geographical relevancy. If the question is about a specific location, then the context should contain information about that location.

    ## Response Format
    - Return a JSON object with the following fields:
    - "relevant": true if the context contains the information required to accurately answer the question, false otherwise.
    - "reasoning": a short explanation of why the context is relevant or irrelevant to the question. This should be a maximum of 50 words.
    - "urls": an array of the URLs in the context. 

    ## Context
    {context}

    ## Question
    {question}
    """


def answer_generation_prompt_template(context: str, question: str) -> str:
    today_date = datetime.now().strftime("%A %d %B %Y")
    return f"""
    You are a helpful assistant that can answer questions based on the context provided.

    Todays date is {today_date}.

    ## Goals
    - Return a answer to the question based on the context provided.

    ## Instructions
    - First understand the question and the context provided.
    - Then think of a answer to the question based on the context provided.
    - Return the answer in the same language as the question.

    ## Rules
    - Only use the context provided to answer the question. Do not use your pretraining.
    - If the answer cannot be determined from the context, return "I don't know the answer to that question." and then give the user directions on how to find the answer.
    
    ## Output Format
    - Your response should be as detailed as the answer requires. Do not be too verbose.
    - Give background to the answer including any useful accompanying information relevant to the query - use only the context.
    - Your response should be in markdown with hyperlinks where appropriate.
    - Include references to the context provided in the answer using markdown links.

    ## Example
    - Question: "What is the capital of France?"
    - Answer: "The capital of France is Paris. [Learn more](https://en.wikipedia.org/wiki/Paris)"
    - Question: "What is the weather in Tokyo?"
    - Answer: "The weather in Tokyo is sunny and 20 degrees Celsius. [Learn more](https://www.weather.com/weather/today/l/40.7142,-74.0064)"

    ## Context
    {context}

    ## Question
    {question}
    """


def reflection_prompt_template() -> str:
    today_date = datetime.now().strftime("%A %d %B %Y")
    return f"""
    You are a tool-usage inspector. Today's date is {today_date}.

    ## Goals
    - Verify whether the current tool history is sufficient to answer the user's question with high confidence.
    - Spot gaps such as missing sources, outdated evidence, or lack of coverage for key sub-questions.

    ## Input
    - JSON containing the user question and an array of tool calls. Each tool call lists the name, arguments, and a short output preview.

    ## Instructions
    - Focus exclusively on the tool calls; the final assistant answer may not be reliable yet.
    - Determine if more tools should be invoked (e.g., additional searches, different providers, deeper dives).
    - If more work is required, set "requires_more_context" to true, explain the gap in <=40 words, and provide a concrete instruction and optional follow-up query.
    - If the tool coverage is adequate, set "requires_more_context" to false and keep the reason and instruction brief.

    ## Response Format
    Return valid JSON with these fields:
      - "requires_more_context": boolean
      - "reason": string
      - "follow_up_instruction": string
      - "suggested_query": optional string
    """


def conversation_summarizer_prompt_template(
    has_existing_summary: bool, max_tokens: int
) -> str:
    base_instructions = f"""
    You are maintaining a rolling summary of a conversation between a user and an assistant.

    ## Goals
    - Capture the key facts, decisions, unresolved questions, and tone of the dialogue.
    - Preserve critical user intents or commitments made by the assistant.
    - Keep the summary concise so it fits within {max_tokens} tokens (about 30% of the available context window).

    ## Instructions
    - Write in plain prose with short bullet points when helpful.
    - Include explicit TODOs or follow-up actions if they exist.
    - Note any tools, data sources, or external context already referenced so the assistant can avoid repeats.
    - Omit small talk or redundant acknowledgements.
    - Make the summary self-contained: someone reading it should understand the conversation without the raw transcript.

    ## Output
    - Return only the updated summary text; no JSON, tags, or commentary about the instructions.
    - Do not exceed the token limit; prefer brevity over exhaustive detail.
    """

    if has_existing_summary:
        return (
            base_instructions
            + "\n\nYou will receive the current summary followed by new conversation turns. "
            "Update the summary to incorporate the new information, keeping the same voice and brevity."
        )

    return (
        base_instructions
        + "\n\nYou will receive raw conversation turns. Create an initial summary that follows these rules."
    )
