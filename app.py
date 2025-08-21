# app.py
import streamlit as st
import pandas as pd
import mysql.connector
from mysql.connector import Error
import plotly.express as px
from io import BytesIO

st.set_page_config(page_title="Food Donation Analytics (MySQL)", layout="wide")
st.title("🍽️ Food Donation — Analytics (MySQL)")

# -------------------------
# DB connection helper
# -------------------------
def get_connection():
    """
    Uses st.secrets['db'] if present; otherwise falls back to environment variables.
    Required keys in st.secrets['db']: host, port, database, user, password
    """
    try:
        # Prefer secrets
        dbconf = st.secrets.get("db", {})
        host = dbconf.get("host") or st.secrets.get("host", None)
        port = int(dbconf.get("port", 3306)) if dbconf.get("port") else int(st.secrets.get("port", 3306))
        database = dbconf.get("database") or st.secrets.get("database", None)
        user = dbconf.get("user") or st.secrets.get("user", None)
        password = dbconf.get("password") or st.secrets.get("password", None)

        if not (host and database and user is not None):
            raise RuntimeError("Database credentials are not configured in st.secrets['db'] or environment.")

        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connection_timeout=10
        )
        return conn
    except Exception as e:
        st.error(f"Unable to create DB connection: {e}")
        return None

# -------------------------
# Cached query runner
# -------------------------
@st.cache_data(ttl=300, show_spinner=False)
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    conn = get_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql(sql, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Query failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# -------------------------
# Predefined 15 queries
# -------------------------
queries = {
    "Q1_Unique_Providers": {
        "label": "1) Unique Providers",
        "sql": "SELECT DISTINCT Name AS Provider_Name FROM cleaned_provider ORDER BY Provider_Name;"
    },
    "Q2_Unique_Receivers": {
        "label": "2) Unique Receivers",
        "sql": "SELECT DISTINCT Name AS Receiver_Name FROM cleaned_receiver ORDER BY Receiver_Name;"
    },
    "Q3_Providers_per_City": {
        "label": "3) Total Providers per City",
        "sql": "SELECT City, COUNT(*) AS total_providers FROM cleaned_provider GROUP BY City ORDER BY total_providers DESC;"
    },
    "Q4_Receivers_per_City": {
        "label": "4) Total Receivers per City",
        "sql": "SELECT City, COUNT(*) AS total_receivers FROM cleaned_receiver GROUP BY City ORDER BY total_receivers DESC;"
    },
    "Q5_Top_Provider_Type": {
        "label": "5) Top Contributing Provider Type (by total quantity)",
        "sql": "SELECT Provider_Type, SUM(Quantity) AS total_contribution FROM cleaned_food GROUP BY Provider_Type ORDER BY total_contribution DESC;"
    },
    "Q6_Provider_Contact_By_City": {
        "label": "6) Provider Contact Info by City",
        "sql": "SELECT DISTINCT City, Name AS Provider_Name, Contact FROM cleaned_provider ORDER BY City, Provider_Name;"
    },
    "Q7_Providers_in_Tinamouth": {
        "label": "7) Provider Details in 'Tinamouth'",
        "sql": "SELECT Name, Type, Address, Contact FROM cleaned_provider WHERE City = 'Tinamouth';"
    },
    "Q8_Receivers_Most_Claims": {
        "label": "8) Receivers with Most Claims (Pending or Completed)",
        "sql": "SELECT Receiver_ID, COUNT(*) AS total_claims FROM cleaned_claim WHERE Status IN ('Pending','Completed') GROUP BY Receiver_ID ORDER BY total_claims DESC;"
    },
    "Q9_Total_Food_Quantity": {
        "label": "9) Total Food Quantity (sum)",
        "sql": "SELECT COALESCE(SUM(Quantity),0) AS total_quantity FROM cleaned_food;"
    },
    "Q10_Location_Highest_Single_Quantity": {
        "label": "10) Location(s) with Highest Single Food Quantity",
        "sql": "SELECT Location, Quantity FROM cleaned_food WHERE Quantity = (SELECT MAX(Quantity) FROM cleaned_food);"
    },
    "Q11_Most_Common_Food_Types": {
        "label": "11) Most Common Food Types (count of items)",
        "sql": "SELECT Food_Type, COUNT(*) AS total_items FROM cleaned_food GROUP BY Food_Type ORDER BY total_items DESC;"
    },
    "Q12_Claims_per_Food": {
        "label": "12) Claims per Food Item",
        "sql": "SELECT f.Food_ID, f.Food_Name, COUNT(c.Claim_ID) AS total_claims FROM cleaned_food f LEFT JOIN cleaned_claim c ON f.Food_ID = c.Food_ID GROUP BY f.Food_ID, f.Food_Name ORDER BY total_claims DESC;"
    },
    "Q13_Provider_with_Most_Successful": {
        "label": "13) Provider with Most Successful (Completed) Claims",
        "sql": "SELECT f.Provider_ID, p.Name AS Provider_Name, COUNT(c.Claim_ID) AS successful_claims FROM cleaned_claim c JOIN cleaned_food f ON c.Food_ID = f.Food_ID JOIN cleaned_provider p ON f.Provider_ID = p.Provider_ID WHERE c.Status = 'Completed' GROUP BY f.Provider_ID, p.Name ORDER BY successful_claims DESC LIMIT 10;"
    },
    "Q14_Claim_Status_Distribution": {
        "label": "14) Claim Status Distribution (counts & %)",
        "sql": "SELECT Status, COUNT(*) AS total_claims, ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM cleaned_claim), 2) AS percentage FROM cleaned_claim GROUP BY Status;"
    },
    "Q15_Avg_Quantity_Claimed_per_Receiver": {
        "label": "15) Average Quantity Claimed per Receiver (Completed)",
        "sql": "SELECT c.Receiver_ID, ROUND(AVG(f.Quantity),2) AS avg_quantity_claimed FROM cleaned_claim c JOIN cleaned_food f ON c.Food_ID = f.Food_ID WHERE c.Status = 'Completed' GROUP BY c.Receiver_ID ORDER BY avg_quantity_claimed DESC;"
    },
}

# -------------------------
# Sidebar: quick connection test
# -------------------------
st.sidebar.header("DB Status")
if st.sidebar.button("Test DB connection"):
    conn = get_connection()
    if conn:
        st.sidebar.success("✅ Connected to DB")
        conn.close()
    else:
        st.sidebar.error("❌ Connection failed — check st.secrets['db'].")

# -------------------------
# Main navigation
# -------------------------
menu = st.sidebar.selectbox("View", ["Analytics (15 queries)", "Sample Dashboard", "Download Report Workbook"])

if menu == "Sample Dashboard":
    st.header("Sample Dashboard (light) — use Analytics for full queries")
    foods = run_query("SELECT * FROM cleaned_food LIMIT 1000;")
    if foods.empty:
        st.info("No food rows or cannot query DB.")
    else:
        # small interactive filters
        locs = ["All"] + sorted(foods["Location"].dropna().unique().tolist())
        sel_loc = st.selectbox("Location", locs)
        ftypes = ["All"] + sorted(foods["Food_Type"].dropna().unique().tolist()) if "Food_Type" in foods.columns else ["All"]
        sel_ftype = st.selectbox("Food Type", ftypes)
        subset = foods.copy()
        if sel_loc != "All":
            subset = subset[subset["Location"] == sel_loc]
        if sel_ftype != "All":
            subset = subset[subset["Food_Type"] == sel_ftype]
        st.dataframe(subset.head(200))
        if "Food_Type" in subset.columns:
            fig = px.bar(subset.groupby("Food_Type")["Quantity"].sum().reset_index(), x="Food_Type", y="Quantity", title="Quantity by Food Type")
            st.plotly_chart(fig, use_container_width=True)

elif menu == "Analytics (15 queries)":
    st.header("Analytics — 15 Predefined Queries")
    st.markdown("Each query shows a table and (where suitable) an interactive chart. Queries are cached for 5 minutes.")

    # Display queries in two-column layout for space
    keys = list(queries.keys())
    for i, key in enumerate(keys, start=1):
        qmeta = queries[key]
        st.subheader(f"{i}. {qmeta['label']}")
        df = run_query(qmeta["sql"])
        if df is None or df.empty:
            st.info("No results (empty or query failed).")
            continue
        st.dataframe(df, use_container_width=True)

        # heuristics for charting
        # - single numeric aggregate with category => bar
        # - status distribution => pie
        # - total quantity scalar => show metric
        cols = df.columns.tolist()
        if len(cols) == 1:
            # single-value result, show metric
            val = df.iloc[0, 0]
            try:
                st.metric(label=qmeta["label"], value=str(val))
            except Exception:
                pass
        elif "percentage" in (c.lower() for c in cols) and "status" in (c.lower() for c in cols):
            # pie chart for status distribution
            try:
                st.plotly_chart(px.pie(df, names=cols[0], values=[c for c in cols if c.lower().startswith("total") or c.lower().endswith("count")][0]), use_container_width=True)
            except Exception:
                pass
        else:
            # if first col is category and second numeric, bar chart
            if df.shape[1] >= 2:
                first_col, second_col = df.columns[0], df.columns[1]
                if pd.api.types.is_numeric_dtype(df[second_col]):
                    fig = px.bar(df, x=first_col, y=second_col, title=qmeta["label"])
                    st.plotly_chart(fig, use_container_width=True)

    st.success("All queries executed (cached).")

elif menu == "Download Report Workbook":
    st.header("Download workbook containing selected query outputs")

    # build workbook dict
    st.markdown("Select which queries to include in the workbook:")
    selections = []
    for key, meta in queries.items():
        checked = st.checkbox(meta["label"], value=False, key=f"cb_{key}")
        if checked:
            selections.append((key, meta))

    if st.button("Generate & Download Workbook"):

        if not selections:
            st.warning("Pick at least one query to include.")
        else:
            reports = {}
            for key, meta in selections:
                df = run_query(meta["sql"])
                # sanitize sheet name
                sheet_name = meta["label"][:31].replace(" ", "_").replace("/", "_")
                if df is None:
                    df = pd.DataFrame()
                reports[sheet_name] = df

            # write to Excel bytes
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                for sheet, df in reports.items():
                    # if empty df, create note
                    if df.empty:
                        pd.DataFrame({"note": ["No results or query failed"]}).to_excel(writer, sheet_name=sheet, index=False)
                    else:
                        df.to_excel(writer, sheet_name=sheet, index=False)
                writer.save()
            buf.seek(0)
            st.download_button("⬇️ Download insights workbook", data=buf.getvalue(), file_name="insights_workbook.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# -------------------------
# Footer / Notes
# -------------------------
st.markdown("---")
st.caption("Notes: Queries run against your MySQL schema. Ensure your tables (cleaned_provider, cleaned_receiver, cleaned_food, cleaned_claim) exist and have expected columns. Use .streamlit/secrets.toml or Streamlit Cloud secrets to configure DB credentials.")


