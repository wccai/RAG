import os
from langchain_ollama import OllamaLLM
from llama_index.embeddings.ollama import OllamaEmbedding
from langchain_core.prompts import ChatPromptTemplate
from elasticsearch import Elasticsearch
from typing import List

# need to set environment variables for es_host, es_admin, es_pass, es_em_index
model = OllamaLLM(model="gemma:2b")
ollama_embedding = OllamaEmbedding(model_name="gemma:2b")
es_host: str = os.getenv("es_host", "...")
es_admin: str = os.getenv("es_admin", "...")
es_pass: str = os.getenv("es_pass", "...")
es_em_index: str = os.getenv("es_em_index", "em_test_index")

es: Elasticsearch = Elasticsearch(
    hosts=es_host,
    basic_auth=(es_admin, es_pass),
)

ptemplate = """
With the conversation context: {context}
Please answer {question}

"""

prompt = ChatPromptTemplate.from_template(ptemplate)
chain = prompt | model

# use elasticsearch to find top similar chunks
def find_top_similar_ones(question: str, topn: int = 10):
    q_em = ollama_embedding.get_query_embedding(question)
    knn_search_body = {
        "field": "em",
        "query_vector": q_em,
        "k": topn,  # Number of nearest neighbors to return
        "num_candidates": 2 * topn,
    }

    knn_response = es.search(
        index=es_em_index,
        knn=knn_search_body,
        source=True,
        size=topn,
    )

    chunks: List[str] = []
    for hit in knn_response["hits"]["hits"]:
        chunks.append((hit["_source"]["chunk"], round(hit["_score"], 3)))
    return chunks


print(find_top_similar_ones("pc games"))


def chat_with_AI_RAG():
    context = ""
    print("Please say sth.")
    while True:
        user_question = input("You: ")
        if user_question.lower() == "bye":
            break

        top_sim_chunks = find_top_similar_ones(user_question, 10)
        print(top_sim_chunks)
        for tc in top_sim_chunks:
            context += f"\n AI: {tc[0]}"

        result = chain.invoke({"context": context, "question": user_question})
        # result = chain.invoke({"context": "", "question": user_question})
        print("AI: ", result)
        context += f"\n User: {user_question} \n AI: {result}"


chat_with_AI_RAG()
