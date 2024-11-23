# AI Assistant by Large Language Model 

[Jupyter Notebook: build LLM and RAG with reddit text.](conversation_reddit.ipynb)

[Jupyter Notebook: get embedding from LLM with PySpark.](conversation_reddit_Spark.ipynb)

[Folder: get embedding from LLM with Airflow and then build chatbot with RAG](llm-airflow-dags)

+ [Build chatbot with RAG and LLM](llm-airflow-dags/chatbot_llm_rag.py)

+ [DAG python file to schedule of getting daily embedding from LLM](llm-airflow-dags/get_embedding_daily.py)

+ [Get daily embedding from LLM](llm-airflow-dags/get_embedding.py)

+ [Update search index for embedding in Elasticsearch](llm-airflow-dags/update_search_index_for_embedding.py)