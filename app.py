import os
import math
import time
import typing as t
from datetime import datetime

import pandas as pd
from dateutil import parser as dateparser
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import streamlit as st

TABLES = {
    "food": "cleaned_food",
    "claim": "cleaned_claim",
    "provider": "cleaned_provider",
    "receiver": "cleaned_receiver",
}


PK = {
    "cleaned_food": "Food_ID",
    "cleaned_claim": "Claim_ID",
    "cleaned_provider": "Provider_ID",
    "cleaned_receiver": "Receiver_ID",
}


CONTACT_COLS = {
    "cleaned_provider": {"name": "Name", "contact": "Contact", "city": "City"},
    "cleaned_receiver": {"name": "Receiver_Name", "contact": "Contact", "city": "City"},
}


@st.cache_resource(show_spinner=False)
def get_engine_from_inputs(user: str, pwd: str, host: str, db: str) -> Engine:
    url = f"mysql+pymysql://{user}:{pwd}@{host}/{db}"
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)

@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    # 1) Try st.secrets
    if "db" in st.secrets:
        s = st.secrets["db"]
        return get_engine_from_inputs(s.get("user", "root"), s.get("password", ""), s.get("host", "localhost"), s.get("database", "foodwastemanagement"))
    # 2) Try env vars
    user = os.getenv("MYSQL_USER", "root")
    pwd = os.getenv("MYSQL_PWD", os.getenv("MYSQL_PASSWORD", ""))
    host = os.getenv("MYSQL_HOST", "localhost")
    db = os.getenv("MYSQL_DB", "foodwastemanagement")
    return get_engine_from_inputs(user, pwd, host, db)

def run_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    eng = get_engine()
    with eng.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)

def exec_sql(sql: str, params: dict | None = None) -> int:
    eng = get_engine()
    with eng.begin() as conn:
        res = conn.execute(text(sql), params or {})
        return res.rowcount if hasattr(res, "rowcount") else 0

def load_table_df(table_name: str) -> pd.DataFrame:
    try:
        return run_sql(f"SELECT * FROM {table_name}")
    except Exception as e:
        st.warning(f"Could not load table '{table_name}'. Error: {e}")
        return pd.DataFrame()


st.set_page_config(page_title="Food Donation Dashboard", layout="wide")
st.title("🍲 Food Donation Dashboard – MySQL")

with st.sidebar:
    st.header("Database Connection")
    st.caption("You can also configure via .streamlit/secrets.toml or env vars.")
    user = st.text_input("User", os.getenv("MYSQL_USER", st.secrets.get("db", {}).get("user", "root")))
    pwd = st.text_input("Password", os.getenv("MYSQL_PWD", st.secrets.get("db", {}).get("password", "")), type="password")
    host = st.text_input("Host", os.getenv("MYSQL_HOST", st.secrets.get("db", {}).get("host", "localhost")))
    database = st.text_input("Database", os.getenv("MYSQL_DB", st.secrets.get("db", {}).get("database", "foodwastemanagement")))
    if st.button("Connect / Refresh", use_container_width=True):
        st.cache_resource.clear()
        get_engine_from_inputs(user, pwd, host, database)
        st.success("Connection refreshed.")


if any([
    user != os.getenv("MYSQL_USER", st.secrets.get("db", {}).get("user", "root")),
    host != os.getenv("MYSQL_HOST", st.secrets.get("db", {}).get("host", "localhost")),
    database != os.getenv("MYSQL_DB", st.secrets.get("db", {}).get("database", "foodwastemanagement")),
]):
    @st.cache_resource(show_spinner=False)
    def _custom_engine():
        return get_engine_from_inputs(user, pwd, host, database)
    def get_engine() -> Engine:  # type: ignore[no-redef]
        return _custom_engine()


st.subheader("🔎 Filters")
food_table = TABLES["food"]
claim_table = TABLES["claim"]
provider_table = TABLES["provider"]
receiver_table = TABLES["receiver"]

food_df = load_table_df(food_table)
claim_df = load_table_df(claim_table)

col1, col2, col3 = st.columns(3)
with col1:
    loc_opts = sorted(food_df["Location"].dropna().unique().tolist()) if not food_df.empty and "Location" in food_df else []
    sel_locations = st.multiselect("Location", loc_opts)
with col2:
    prov_opts = sorted(food_df["Provider_ID"].dropna().unique().tolist()) if not food_df.empty and "Provider_ID" in food_df else []
    sel_providers = st.multiselect("Provider ID", prov_opts)
with col3:
    ftype_opts = sorted(food_df["Food_Type"].dropna().unique().tolist()) if not food_df.empty and "Food_Type" in food_df else []
    sel_food_types = st.multiselect("Food Type", ftype_opts)

if not food_df.empty:
    f_filt = food_df.copy()
    if sel_locations:
        f_filt = f_filt[f_filt["Location"].isin(sel_locations)]
    if sel_providers:
        f_filt = f_filt[f_filt["Provider_ID"].isin(sel_providers)]
    if sel_food_types:
        f_filt = f_filt[f_filt["Food_Type"].isin(sel_food_types)]
    st.dataframe(f_filt, use_container_width=True)
else:
    st.info("Load your food table to see filterable results.")


st.subheader("📞 Contact Providers & Receivers")
cc1, cc2 = st.columns(2)

with cc1:
    st.markdown("**Providers**")
    prov_df = load_table_df(provider_table)
    if not prov_df.empty:
        cols = CONTACT_COLS.get(provider_table, {})
        name_col = cols.get("name", "Name")
        contact_col = cols.get("contact", "Contact")
        city_col = cols.get("city", "City")
        view = prov_df[[c for c in [PK[provider_table], name_col, city_col, contact_col] if c in prov_df.columns]].copy()
        if contact_col in view.columns:
            # make tel/mailto links
            def _mk_link(v: str) -> str:
                v = str(v)
                if "@" in v:
                    return f"[Email]('mailto:{v}')"
                return f"[Call]('tel:{v}')"
            view["Contact_Link"] = view[contact_col].apply(_mk_link)
        st.dataframe(view, use_container_width=True)
    else:
        st.info("Provider table not available.")

with cc2:
    st.markdown("**Receivers**")
    rec_df = load_table_df(receiver_table)
    if not rec_df.empty:
        cols = CONTACT_COLS.get(receiver_table, {"name": "Receiver_Name", "contact": "Contact", "city": "City"})
        name_col = cols.get("name", "Receiver_Name")
        contact_col = cols.get("contact", "Contact")
        city_col = cols.get("city", "City")
        view = rec_df[[c for c in [PK[receiver_table], name_col, city_col, contact_col] if c in rec_df.columns]].copy()
        if contact_col in view.columns:
            def _mk_link(v: str) -> str:
                v = str(v)
                if "@" in v:
                    return f"[Email]('mailto:{v}')"
                return f"[Call]('tel:{v}')"
            view["Contact_Link"] = view[contact_col].apply(_mk_link)
        st.dataframe(view, use_container_width=True)
    else:
        st.info("Receiver table not available.")

with st.expander("✉️ Quick Email Composer"):
    to_email = st.text_input("To (email)")
    subject = st.text_input("Subject", "Food Donation")
    body = st.text_area("Body")
    if st.button("Open email in client"):
        import urllib.parse as ul
        url = f"mailto:{to_email}?subject={ul.quote(subject)}&body={ul.quote(body)}"
        st.markdown(f"Open: [{url}]({url})")

import streamlit as st
import mysql.connector
import pandas as pd

# --- DATABASE CONNECTION ---
def get_connection():
    return mysql.connector.connect(
        host=st.secrets["db"]["host"],
        user=st.secrets["db"]["user"],
        password=st.secrets["db"]["password"],
        database=st.secrets["db"]["database"]
    )

# --- READ FUNCTION ---
def fetch_data(query):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query)
    data = cursor.fetchall()
    conn.close()
    return pd.DataFrame(data)

# --- EXECUTE FUNCTION (INSERT, UPDATE, DELETE) ---
def execute_query(query, params=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params or ())
    conn.commit()
    conn.close()

# --- STREAMLIT APP START ---
st.set_page_config(page_title="Food Donation Management", layout="wide")
st.title("🍽️ Food Waste Management - CRUD Operations")

menu = ["Providers", "Receivers", "Food", "Claims"]
choice = st.sidebar.selectbox("Select Table", menu)

# --- CRUD FOR PROVIDERS TABLE ---
if choice == "Providers":
    st.header("Manage Food Providers")
    action = st.selectbox("Select Action", ["View", "Add", "Update", "Delete"])

    if action == "View":
        df = fetch_data("SELECT * FROM cleaned_provider;")
        st.dataframe(df)

    elif action == "Add":
        name = st.text_input("Provider Name")
        provider_type = st.text_input("Provider Type")
        address = st.text_area("Address")
        city = st.text_input("City")
        contact = st.text_input("Contact")

        if st.button("Add Provider"):
            execute_query(
                "INSERT INTO cleaned_provider(Name, Type, Address, City, Contact) VALUES (%s, %s, %s, %s, %s)",
                (name, provider_type, address, city, contact)
            )
            st.success("Provider added successfully ✅")

    elif action == "Update":
        df = fetch_data("SELECT * FROM cleaned_provider;")
        provider_ids = df["Provider_ID"].tolist()
        selected_id = st.selectbox("Select Provider ID", provider_ids)

        new_name = st.text_input("New Name")
        new_type = st.text_input("New Type")
        new_city = st.text_input("New City")
        new_contact = st.text_input("New Contact")

        if st.button("Update Provider"):
            execute_query(
                "UPDATE cleaned_provider SET Name=%s, Type=%s, City=%s, Contact=%s WHERE Provider_ID=%s",
                (new_name, new_type, new_city, new_contact, selected_id)
            )
            st.success("Provider updated successfully ✅")

    elif action == "Delete":
        df = fetch_data("SELECT * FROM cleaned_provider;")
        provider_ids = df["Provider_ID"].tolist()
        selected_id = st.selectbox("Select Provider ID to Delete", provider_ids)

        if st.button("Delete Provider"):
            execute_query("DELETE FROM cleaned_provider WHERE Provider_ID=%s", (selected_id,))
            st.success("Provider deleted successfully ✅")

# --- CRUD FOR RECEIVERS TABLE ---
elif choice == "Receivers":
    st.header("Manage Food Receivers")
    action = st.selectbox("Select Action", ["View", "Add", "Update", "Delete"])

    if action == "View":
        df = fetch_data("SELECT * FROM cleaned_receiver;")
        st.dataframe(df)

    elif action == "Add":
        name = st.text_input("Receiver Name")
        address = st.text_area("Address")
        city = st.text_input("City")
        contact = st.text_input("Contact")

        if st.button("Add Receiver"):
            execute_query(
                "INSERT INTO cleaned_receiver (Name, Address, City, Contact) VALUES (%s, %s, %s, %s)",
                (name, address, city, contact)
            )
            st.success("Receiver added successfully ✅")

    elif action == "Update":
        df = fetch_data("SELECT * FROM cleaned_receiver;")
        receiver_ids = df["Receiver_ID"].tolist()
        selected_id = st.selectbox("Select Receiver ID", receiver_ids)

        new_name = st.text_input("New Name")
        new_city = st.text_input("New City")
        new_contact = st.text_input("New Contact")

        if st.button("Update Receiver"):
            execute_query(
                "UPDATE cleaned_receiver SET Name=%s, City=%s, Contact=%s WHERE Receiver_ID=%s",
                (new_name, new_city, new_contact, selected_id)
            )
            st.success("Receiver updated successfully ✅")

    elif action == "Delete":
        df = fetch_data("SELECT * FROM cleaned_receiver;")
        receiver_ids = df["Receiver_ID"].tolist()
        selected_id = st.selectbox("Select Receiver ID to Delete", receiver_ids)

        if st.button("Delete Receiver"):
            execute_query("DELETE FROM cleaned_receiver WHERE Receiver_ID=%s", (selected_id,))
            st.success("Receiver deleted successfully ✅")

# --- CRUD FOR FOOD TABLE ---
elif choice == "Food":
    st.header("Manage Food Items")
    action = st.selectbox("Select Action", ["View", "Add", "Update", "Delete"])

    if action == "View":
        df = fetch_data("SELECT * FROM cleaned_food;")
        st.dataframe(df)

    elif action == "Add":
        name = st.text_input("Food Name")
        quantity = st.number_input("Quantity", min_value=1)
        expiry = st.date_input("Expiry Date")
        provider_id = st.number_input("Provider ID")
        provider_type = st.text_input("Provider Type")
        location = st.text_input("Location")
        food_type = st.text_input("Food Type")
        meal_type = st.text_input("Meal Type")

        if st.button("Add Food"):
            execute_query(
                "INSERT INTO cleaned_food (Food_Name, Quantity, Expiry_Date, Provider_ID, Provider_Type, Location, Food_Type, Meal_Type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (name, quantity, expiry, provider_id, provider_type, location, food_type, meal_type)
            )
            st.success("Food item added successfully ✅")

    elif action == "Update":
        df = fetch_data("SELECT * FROM cleaned_food;")
        food_ids = df["Food_ID"].tolist()
        selected_id = st.selectbox("Select Food ID", food_ids)

        new_quantity = st.number_input("New Quantity", min_value=1)
        new_expiry = st.date_input("New Expiry Date")

        if st.button("Update Food"):
            execute_query(
                "UPDATE cleaned_food SET Quantity=%s, Expiry_Date=%s WHERE Food_ID=%s",
                (new_quantity, new_expiry, selected_id)
            )
            st.success("Food item updated successfully ✅")

    elif action == "Delete":
        df = fetch_data("SELECT * FROM cleaned_food;")
        food_ids = df["Food_ID"].tolist()
        selected_id = st.selectbox("Select Food ID to Delete", food_ids)

        if st.button("Delete Food"):
            execute_query("DELETE FROM cleaned_food WHERE Food_ID=%s", (selected_id,))
            st.success("Food item deleted successfully ✅")

# --- CRUD FOR CLAIMS TABLE ---
elif choice == "Claims":
    st.header("Manage Food Claims")
    action = st.selectbox("Select Action", ["View", "Add", "Update", "Delete"])

    if action == "View":
        df = fetch_data("SELECT * FROM cleaned_claim;")
        st.dataframe(df)

    elif action == "Add":
        food_id = st.number_input("Food ID")
        receiver_id = st.number_input("Receiver ID")
        status = st.selectbox("Status", ["Pending", "Successful", "Cancelled"])
        timestamp = st.date_input("Timestamp")

        if st.button("Add Claim"):
            execute_query(
                "INSERT INTO cleaned_claim (Food_ID, Receiver_ID, Status, Timestamp) VALUES (%s,%s,%s,%s)",
                (food_id, receiver_id, status, timestamp)
            )
            st.success("Claim added successfully ✅")

    elif action == "Update":
        df = fetch_data("SELECT * FROM cleaned_claim;")
        claim_ids = df["Claim_ID"].tolist()
        selected_id = st.selectbox("Select Claim ID", claim_ids)

        new_status = st.selectbox("New Status", ["Pending", "Successful", "Cancelled"])

        if st.button("Update Claim"):
            execute_query(
                "UPDATE cleaned_claim SET Status=%s WHERE Claim_ID=%s",
                (new_status, selected_id)
            )
            st.success("Claim updated successfully ✅")

    elif action == "Delete":
        df = fetch_data("SELECT * FROM cleaned_claim;")
        claim_ids = df["Claim_ID"].tolist()
        selected_id = st.selectbox("Select Claim ID to Delete", claim_ids)

        if st.button("Delete Claim"):
            execute_query("DELETE FROM cleaned_claim WHERE Claim_ID=%s", (selected_id,))
            st.success("Claim deleted successfully ✅")

import streamlit as st
import pandas as pd
import mysql.connector

# DB Connection
def get_connection():
    return mysql.connector.connect(
        host="localhost",        # Change as needed
        user="root",    # <-- Replace
        password="123456",# <-- Replace
        database="foodwastemanagement" # <-- Replace
    )

def run_query(query):
    conn = get_connection()
    df = pd.read_sql(query, conn)
    conn.close()
    return df

st.set_page_config(page_title="Food Dashboard", layout="wide")
st.title("🍽️ Food Queries Dashboard")

queries = {
    "1. Unique Providers": "SELECT DISTINCT Name FROM cleaned_provider;",
    "2. Unique Receivers": "SELECT DISTINCT Name FROM cleaned_receiver;",
    "3. Total Providers per City": """
        SELECT city, COUNT(*) AS total_providers
        FROM cleaned_provider
        GROUP BY city
        ORDER BY total_providers DESC;
    """,
    "4. Total Receivers per City": """
        SELECT city, COUNT(*) AS total_receivers
        FROM cleaned_receiver
        GROUP BY city
        ORDER BY total_receivers DESC;
    """,
    "5. Top Contributing Provider Type": """
        SELECT provider_type, SUM(quantity) AS total_contribution
        FROM cleaned_food
        GROUP BY provider_type
        ORDER BY total_contribution DESC
        LIMIT 1;
    """,
    "6. Provider Contact Info by City": """
        SELECT DISTINCT city, contact FROM cleaned_provider;
    """,
    "7. Provider Details in 'Tinamouth'": """
        SELECT name, type, address, contact
        FROM cleaned_provider
        WHERE city = 'Tinamouth';
    """,
    "8. Receivers with Most Claims": """
        SELECT Receiver_ID, COUNT(*) AS total_claims
        FROM cleaned_claim
        WHERE Status = 'Pending' OR Status = 'Completed'
        GROUP BY Receiver_ID
        ORDER BY total_claims DESC;
    """,
    "9. Total Food Quantity": "SELECT SUM(quantity) FROM cleaned_food;",
    "10. Location with Highest Food Quantity": """
        SELECT location
        FROM cleaned_food
        WHERE quantity = (SELECT MAX(quantity) FROM cleaned_food);
    """,
    "11. Most Common Food Types": """
        SELECT Food_Type, COUNT(*) AS total_items
        FROM cleaned_food
        GROUP BY Food_Type
        ORDER BY total_items DESC;
    """,
    "12. Claims per Food Item": """
        SELECT f.Food_Name, COUNT(c.Claim_ID) AS total_claims
        FROM cleaned_food f
        INNER JOIN cleaned_claim c ON f.Food_ID = c.Food_ID
        GROUP BY f.Food_Name
        ORDER BY total_claims DESC;
    """,
    "13. Provider with Most Successful Claims": """
        SELECT f.Provider_ID, f.Provider_Type, COUNT(c.Claim_ID) AS successful_claims
        FROM cleaned_claim c
        INNER JOIN cleaned_food f ON c.Food_ID = f.Food_ID
        WHERE c.Status = 'Completed'
        GROUP BY f.Provider_ID, f.Provider_Type
        ORDER BY successful_claims DESC
        LIMIT 1;
    """,
    "14. Claim Status Distribution": """
        SELECT Status, COUNT(*) AS total_claims,
               ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM cleaned_claim)), 2) AS percentage
        FROM cleaned_claim
        GROUP BY Status;
    """,
    "15. Avg Quantity Claimed per Receiver": """
        SELECT c.Receiver_ID,
               ROUND(AVG(f.Quantity), 2) AS avg_quantity_claimed
        FROM cleaned_claim c
        INNER JOIN cleaned_food f ON c.Food_ID = f.Food_ID
        WHERE c.Status = 'Completed'
        GROUP BY c.Receiver_ID
        ORDER BY avg_quantity_claimed DESC;
    """,
    "16. Most Claimed Meal Type": """
        SELECT f.Meal_Type, COUNT(c.Claim_ID) AS total_claims
        FROM cleaned_claim c
        INNER JOIN cleaned_food f ON c.Food_ID = f.Food_ID
        WHERE c.Status = 'Completed'
        GROUP BY f.Meal_Type
        ORDER BY total_claims DESC
        LIMIT 1;
    """,
    "17. Total Quantity Donated by Provider": """
        SELECT Provider_ID, Provider_Type, SUM(Quantity) AS total_quantity_donated
        FROM cleaned_food
        GROUP BY Provider_ID, Provider_Type
        ORDER BY Provider_Type DESC;
    """
}

# Display each query and result
for label, sql in queries.items():
    st.subheader(label)
    try:
        result = run_query(sql)
        st.dataframe(result)
    except Exception as e:
        st.error(f"Error running query: {e}")

import streamlit as st
import pandas as pd
import plotly.express as px

# ---------------------------------
# App Title
# ---------------------------------
st.set_page_config(page_title="Food Wastage Analysis", layout="wide")
st.title("🥗 Food Wastage & Distribution Dashboard")

# ---------------------------------
# Step 1: Upload Excel Files
# ---------------------------------
st.sidebar.header("📂 Upload Data Files (.xlsx)")

provider_file = st.sidebar.file_uploader("Upload Provider Data", type=["xlsx"])
receiver_file = st.sidebar.file_uploader("Upload Receiver Data", type=["xlsx"])
food_file = st.sidebar.file_uploader("Upload Food Listing Data", type=["xlsx"])
claim_file = st.sidebar.file_uploader("Upload Claim Data", type=["xlsx"])

if provider_file and receiver_file and food_file and claim_file:
    # Load data
    cleaned_provider = pd.read_excel(provider_file)
    cleaned_receiver = pd.read_excel(receiver_file)
    cleaned_food = pd.read_excel(food_file)
    cleaned_claim = pd.read_excel(claim_file)

    # Convert date columns
    cleaned_food['Expiry_Date'] = pd.to_datetime(cleaned_food['Expiry_Date'])
    cleaned_claim['Timestamp'] = pd.to_datetime(cleaned_claim['Timestamp'])

    # Merge food with providers
    food_provider = pd.merge(cleaned_food, cleaned_provider, on='Provider_ID', how='left')
    # Merge claims with food-provider and receivers
    claim_food = pd.merge(cleaned_claim, food_provider, on='Food_ID', how='left')
    full_data = pd.merge(claim_food, cleaned_receiver, on='Receiver_ID', how='left')

    # ---------------------------------
    # Step 2: Key Metrics
    # ---------------------------------
    st.subheader("📊 Key Statistics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Providers", cleaned_provider['Provider_ID'].nunique())
    col2.metric("Total Receivers", cleaned_receiver['Receiver_ID'].nunique())
    col3.metric("Total Food Items", cleaned_food['Food_ID'].nunique())
    col4.metric("Total Claims", cleaned_claim['Claim_ID'].nunique())

    # ---------------------------------
    # Step 3: Food Wastage Trends
    # ---------------------------------
    st.subheader("🍽️ Food Wastage Analysis")

    # Wastage by Food Type
    wastage_by_type = full_data.groupby('Food_Type')['Quantity'].sum().reset_index()
    fig1 = px.bar(wastage_by_type, x='Food_Type', y='Quantity', color='Food_Type',
                  title="Food Wastage by Food Type")
    st.plotly_chart(fig1, use_container_width=True)

    # Wastage by Meal Type
    wastage_by_meal = full_data.groupby('Meal_Type')['Quantity'].sum().reset_index()
    fig2 = px.pie(wastage_by_meal, names='Meal_Type', values='Quantity',
                  title="Food Wastage by Meal Type")
    st.plotly_chart(fig2, use_container_width=True)

    # Wastage by Location
    wastage_by_location = full_data.groupby('Location')['Quantity'].sum().reset_index()
    fig3 = px.bar(wastage_by_location, x='Location', y='Quantity', color='Location',
                  title="Food Wastage by Location")
    st.plotly_chart(fig3, use_container_width=True)

    # ---------------------------------
    # Step 4: Near-Expiry Food
    # ---------------------------------
    st.subheader("⏳ Food Items Nearing Expiry")
    today = pd.Timestamp.today()
    near_expiry = full_data[full_data['Expiry_Date'] <= today + pd.Timedelta(days=3)]
    st.dataframe(near_expiry[['Food_Name', 'Quantity', 'Expiry_Date', 'Provider_ID', 'Location']])

    # ---------------------------------
    # Step 5: Claims Overview
    # ---------------------------------
    st.subheader("📦 Claims Overview")

    tab1, tab2, tab3 = st.tabs(["✅ Completed", "⏳ Pending", "❌ Cancelled"])

    with tab1:
        completed_claim = full_data[full_data['Status'] == 'Completed']
        st.dataframe(completed_claim[['Claim_ID', 'Food_Name', 'Quantity', 'Name_y', 'Location']])

    with tab2:
        pending_claim = full_data[full_data['Status'] == 'Pending']
        st.dataframe(pending_claim[['Claim_ID', 'Food_Name', 'Quantity', 'Name_y', 'Location']])

    with tab3:
        cancelled_claim = full_data[full_data['Status'] == 'Cancelled']
        st.dataframe(cancelled_claim[['Claim_ID', 'Food_Name', 'Quantity', 'Name_y', 'Location']])

    
else:
    st.info("👈 Please upload all four Excel files to begin analysis.")


