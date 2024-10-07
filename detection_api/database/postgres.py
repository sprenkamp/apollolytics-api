from sqlalchemy import create_engine, MetaData, Table, Column, String, Text, insert, select, inspect, and_, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func
from dotenv import load_dotenv
import os
import json
import logging

load_dotenv()

POSTGRES_URL = os.getenv("POSTGRES_URL")

print(f"Connecting to database at {POSTGRES_URL}")

# Create engine and session
engine = create_engine(POSTGRES_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
metadata = MetaData()

# Define the 'analysis_results' table schema
analysis_results_table = Table(
    'analysis_results', metadata,
    Column('user_id', String, primary_key=True),
    Column('request_time', DateTime(timezone=True), server_default=func.now()),  # Current time
    Column('model_name', String),
    Column('text', Text),
    Column('contextualize', String),
    Column('result', Text)  # Store the result as JSON string
)

# Check if the table exists and create it if necessary
def ensure_analysis_results_table_exists():
    inspector = inspect(engine)
    if not inspector.has_table("analysis_results"):
        # Table doesn't exist, create it
        metadata.create_all(engine)
        print("Table 'analysis_results' created.")
    else:
        return None

# Function to save request to database
def save_request_to_db(user_id, model_name, text, contextualize, result):
    ensure_analysis_results_table_exists()
    session = SessionLocal()
    try:
        # Create a new record
        new_record = {
            'user_id': user_id,
            'model_name': model_name,
            'text': text,
            'contextualize': str(contextualize),
            'result': json.dumps(result)
        }

        # Insert the new record
        query = insert(analysis_results_table).values(new_record)
        session.execute(query)
        session.commit()
        logging.info(f"Analysis result for user {user_id} saved successfully.")
    except SQLAlchemyError as e:
        logging.error(f"Error saving analysis result: {e}")
        session.rollback()
    finally:
        session.close()

# Function to find analysis results based on filters
def find_db_items(**filters):
    """
    Find analysis results based on one or more attributes. If no filters are provided, all results will be returned.

    Available filters:
    - id
    - user_id
    - model_name
    - text
    - contextualize
    - result

    Example usage:
    - find_analysis_results(user_id='1234', model_name='gpt-4o')
    - find_analysis_results()  # Returns the whole table if no filters are applied
    """
    
    session = SessionLocal()
    try:
        # Start with a select query
        query = select(analysis_results_table)

        # If filters are provided, apply them
        if filters:
            conditions = [getattr(analysis_results_table.c, key) == value for key, value in filters.items()]
            query = query.where(and_(*conditions))

        # Execute the query
        result = session.execute(query).mappings().all()

        # Return results as list of dictionaries
        analysis_results = []
        for row in result:
            row_dict = dict(row)
            # Deserialize the 'result' field from JSON string to dictionary
            row_dict['result'] = json.loads(row_dict['result'])
            analysis_results.append(row_dict)

        return analysis_results

    except SQLAlchemyError as e:
        print(f"Error finding analysis results: {e}")
    finally:
        session.close()
