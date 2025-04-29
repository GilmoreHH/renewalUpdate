import streamlit as st
from simple_salesforce import Salesforce
import os
from dotenv import load_dotenv
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import datetime

# Load environment variables from .env file
load_dotenv()

# Set page configuration
st.set_page_config(
    page_title="Renewals Breakdown Dashboard",
    page_icon="📊",
    layout="wide",
)

# Define all stages and their simplified categories
def get_stage_metadata():
    """Return a dictionary of stages with their categories."""
    stages = {
        "New": {"category": "Open"},
        "Information Gathering": {"category": "Open"},
        "Rating": {"category": "Open"},
        "Proposal Generation": {"category": "Open"},
        "Decision Pending": {"category": "Open"},
        "Pre-Bind Review": {"category": "Open"},
        "Quote to Bind": {"category": "Open"},
        "Binding": {"category": "Open"},
        "Billing": {"category": "Open"},
        "Post-Binding": {"category": "Open"},
        "Closed Won": {"category": "Won"},
        "Closed Lost": {"category": "Lost"}
    }
    return stages

# Function to get current ISO week
def get_current_iso_week():
    """Calculate the ISO week number for the current date."""
    today = datetime.date.today()
    year, week_num, _ = today.isocalendar()
    return year, week_num

# Function to connect to Salesforce and run SOQL queries
def connect_to_salesforce(start_date=None, end_date=None):
    """Connect to Salesforce and execute SOQL queries with optional date range."""
    try:
        # Salesforce connection using environment variables
        sf = Salesforce(
            username=os.getenv("SF_USERNAME_PRO"),
            password=os.getenv("SF_PASSWORD_PRO"),
            security_token=os.getenv("SF_SECURITY_TOKEN_PRO"),
        )

        # Get stage metadata
        stage_metadata = get_stage_metadata()
        
        # Prepare date filter
        date_filter = ""
        if start_date and end_date:
            # Convert dates to Salesforce date format (YYYY-MM-DD)
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')
            date_filter = f"AND CloseDate >= {start_date_str} AND CloseDate <= {end_date_str}"
        
        # First approach: Query both Accounts and User information in one step
        # Using a simple query that just gets the Account Manager's Name
        account_query = """
            SELECT 
                Id, 
                Name,
                Account_Manager__c,
                Account_Manager__r.Name
            FROM Account
            WHERE Account_Manager__c != null
        """
        
        try:
            # Also try a separate query to get user information
            # Get User information that might be associated with the Account Manager
            user_query = """
                SELECT 
                    Id,
                    Name,
                    FirstName,
                    LastName
                FROM User
                WHERE IsActive = true
            """
            
            # Execute both queries
            account_results = sf.query_all(account_query)
            user_results = sf.query_all(user_query)
            
            # Create a map of user names
            user_map = {}
            for user in user_results['records']:
                # Create both full and partial name mappings for flexible matching
                user_id = user['Id']
                full_name = user['Name']
                first_name = user.get('FirstName', '')
                last_name = user.get('LastName', '')
                
                # Map all variations
                user_map[user_id] = {'full_name': full_name, 'first_name': first_name, 'last_name': last_name}
            
            # Create a dictionary to map Account IDs to their Account Managers
            account_manager_map = {}
            for record in account_results['records']:
                account_id = record['Id']
                # Get the Account Manager name from the relationship
                producer_name = record.get('Account_Manager__r', {}).get('Name', 'Not Assigned')
                account_manager_map[account_id] = producer_name
            
        except Exception as e:
            st.warning(f"Error in queries: {str(e)}")
            # Fallback approach - just try the simplest query
            fallback_query = """
                SELECT 
                    Id, 
                    Name,
                    Account_Manager__c,
                    Account_Manager__r.Name
                FROM Account
                WHERE Account_Manager__c != null
            """
            
            account_results = sf.query_all(fallback_query)
            
            # Create a dictionary to map Account IDs to their Account Managers (using just the Name)
            account_manager_map = {}
            for record in account_results['records']:
                account_id = record['Id']
                account_manager = record.get('Account_Manager__r', {}).get('Name', 'Not Assigned')
                account_manager_map[account_id] = account_manager
        
        # Now query Opportunity records with Account relationship
        opportunity_query = f"""
            SELECT 
                Id, 
                StageName, 
                Type,
                AccountId,
                Account.Name,
                New_Business_or_Renewal__c,
                CloseDate
            FROM Opportunity
            WHERE New_Business_or_Renewal__c IN ('Personal Lines - Renewal', 'Commercial Lines - Renewal')
            {date_filter}
        """
        
        opportunity_results = sf.query_all(opportunity_query)
        
        # Process results into a DataFrame
        data = []
        for record in opportunity_results['records']:
            stage_name = record['StageName']
            renewal_type = record['New_Business_or_Renewal__c']
            business_type = record.get('Type', 'Not Specified')
            account_id = record['AccountId']
            
            # Get account manager from the account_manager_map
            account_manager = account_manager_map.get(account_id, "Not Assigned")
            
            # Get stage category
            category = stage_metadata.get(stage_name, {"category": "Unknown"})["category"]
            
            data.append({
                'StageName': stage_name,
                'StatusCategory': category,
                'RenewalType': renewal_type,
                'BusinessType': business_type,
                'AccountManager': account_manager,
                'CloseDate': record['CloseDate'],
                'AccountName': record.get('Account', {}).get('Name', 'Unknown Account')
            })
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        return df
    
    except Exception as e:
        st.error(f"Error connecting to Salesforce: {str(e)}")
        return pd.DataFrame()

# Streamlit UI
st.title("Renewal Opportunities Breakdown Dashboard")

# Get current date and ISO week information
today = datetime.datetime.today()
iso_year, iso_week = get_current_iso_week()

# Display current date
st.info(f"Today: {today.strftime('%A, %B %d, %Y')}")

# Sidebar for user interaction
st.sidebar.header("Dashboard Options")

# Date range selection
st.sidebar.subheader("Date Range Selection")
date_range_type = st.sidebar.radio(
    "Select Date Range Type",
    ["Predefined", "Custom"]
)

# Date range logic
if date_range_type == "Predefined":
    time_period = st.sidebar.selectbox(
        "Select Time Period",
        options=["Last 7 Days", "Last 30 Days", "Last Quarter", "Year to Date"],
        index=1
    )
    
    # Determine dates based on selection
    if time_period == "Last 7 Days":
        start_date = today - datetime.timedelta(days=7)
        end_date = today
    elif time_period == "Last 30 Days":
        start_date = today - datetime.timedelta(days=30)
        end_date = today
    elif time_period == "Last Quarter":
        start_date = today - datetime.timedelta(days=90)
        end_date = today
    else:  # Year to Date
        start_date = datetime.datetime(today.year, 1, 1).date()
        end_date = today
else:
    # Custom date range
    start_date = st.sidebar.date_input(
        "Start Date", 
        value=today - datetime.timedelta(days=30),
        max_value=today
    )
    end_date = st.sidebar.date_input(
        "End Date", 
        value=today,
        max_value=today
    )

    # Validate dates
    if start_date > end_date:
        st.sidebar.error("Start date must be before or equal to end date.")
        start_date, end_date = end_date, start_date

# View options
view_by = st.sidebar.radio(
    "View Breakdown By",
    ["Both", "Line of Business", "Account Manager"]
)

# Additional options
show_data_table = st.sidebar.checkbox("Show Data Tables", value=True)
show_percentages = st.sidebar.checkbox("Show Percentages", value=True)

# Fetch data
df = connect_to_salesforce(start_date, end_date)

if not df.empty:
    # Display reporting period
    st.subheader("Reporting Period")
    st.info(f"From: {start_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}")
    
    # Overall summary metrics
    st.subheader("Renewal Opportunities Summary")
    col1, col2, col3, col4 = st.columns(4)
    
    total_opps = len(df)
    won_opps = len(df[df['StatusCategory'] == 'Won'])
    lost_opps = len(df[df['StatusCategory'] == 'Lost'])
    open_opps = len(df[df['StatusCategory'] == 'Open'])
    
    with col1:
        st.metric("Total Opportunities", total_opps)
    with col2:
        st.metric("Won", won_opps)
    with col3:
        st.metric("Lost", lost_opps)
    with col4:
        st.metric("Open", open_opps)
    
    # Calculate win rate
    if (won_opps + lost_opps) > 0:
        win_rate = (won_opps / (won_opps + lost_opps)) * 100
    else:
        win_rate = 0
    
    # Win Rate Gauge
    st.subheader("Win Rate")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=win_rate,
        title={"text": "Win Rate (%)"},
        number={"suffix": "%", "valueformat": ".2f"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#1f77b4"},
            "steps": [
                {"range": [0, 50], "color": "#e74c3c"},
                {"range": [50, 75], "color": "#f39c12"},
                {"range": [75, 100], "color": "#2ecc71"}
            ],
        }
    ))
    st.plotly_chart(fig)
    
    # Line of Business Analysis
    if view_by in ["Both", "Line of Business"]:
        st.header("Breakdown by Line of Business")
        
        # Get counts by business type and status
        lob_status_df = df.groupby(['BusinessType', 'StatusCategory']).size().reset_index(name='Count')
        
        # Pivot for better visualization
        lob_pivot = lob_status_df.pivot(index='BusinessType', columns='StatusCategory', values='Count').fillna(0)
        
        # Ensure all categories exist
        for category in ['Won', 'Lost', 'Open']:
            if category not in lob_pivot.columns:
                lob_pivot[category] = 0
        
        # Total by line of business
        lob_pivot['Total'] = lob_pivot.sum(axis=1)
        
        # Calculate percentages
        if show_percentages:
            for category in ['Won', 'Lost', 'Open']:
                lob_pivot[f'{category}_Pct'] = (lob_pivot[category] / lob_pivot['Total'] * 100).round(1)
        
        # Stacked bar chart
        lob_melted = lob_status_df.copy()
        
        fig = px.bar(
            lob_melted,
            x="BusinessType",
            y="Count",
            color="StatusCategory",
            title="Renewal Status by Line of Business",
            color_discrete_map={
                "Won": "#2ecc71", 
                "Lost": "#e74c3c",
                "Open": "#f39c12"
            },
            barmode="stack"
        )
        fig.update_layout(xaxis_title="Line of Business", yaxis_title="Number of Opportunities")
        st.plotly_chart(fig)
        
        # Show data table
        if show_data_table:
            st.subheader("Line of Business Breakdown")
            display_df = lob_pivot.reset_index()
            
            # Format the table
            if show_percentages:
                display_df = display_df[['BusinessType', 'Won', 'Won_Pct', 'Lost', 'Lost_Pct', 'Open', 'Open_Pct', 'Total']]
                display_df.columns = ['Line of Business', 'Won', 'Won %', 'Lost', 'Lost %', 'Open', 'Open %', 'Total']
            else:
                display_df = display_df[['BusinessType', 'Won', 'Lost', 'Open', 'Total']]
                display_df.columns = ['Line of Business', 'Won', 'Lost', 'Open', 'Total']
            
            st.dataframe(display_df)
    
    # Account Manager Analysis
    if view_by in ["Both", "Account Manager"]:
        st.header("Breakdown by Account Manager")
        
        # Get counts by account manager and status
        am_status_df = df.groupby(['AccountManager', 'StatusCategory']).size().reset_index(name='Count')
        
        # Pivot for better visualization
        am_pivot = am_status_df.pivot(index='AccountManager', columns='StatusCategory', values='Count').fillna(0)
        
        # Ensure all categories exist
        for category in ['Won', 'Lost', 'Open']:
            if category not in am_pivot.columns:
                am_pivot[category] = 0
        
        # Total by account manager
        am_pivot['Total'] = am_pivot.sum(axis=1)
        
        # Calculate win rate for each account manager
        closed_ops = am_pivot['Won'] + am_pivot['Lost']
        am_pivot['Win_Rate'] = (am_pivot['Won'] / closed_ops * 100).fillna(0).round(1)
        
        # Calculate percentages
        if show_percentages:
            for category in ['Won', 'Lost', 'Open']:
                am_pivot[f'{category}_Pct'] = (am_pivot[category] / am_pivot['Total'] * 100).round(1)
        
        # Sort by total opportunities
        am_pivot = am_pivot.sort_values('Total', ascending=False)
        
        # Filter for visualization (top 10 for clarity)
        top_managers = am_pivot.head(10).index.tolist()
        am_melted_filtered = am_status_df[am_status_df['AccountManager'].isin(top_managers)]
        
        # Stacked bar chart
        fig = px.bar(
            am_melted_filtered,
            x="AccountManager",
            y="Count",
            color="StatusCategory",
            title="Renewal Status by Account Manager (Top 10 by Volume)",
            color_discrete_map={
                "Won": "#2ecc71", 
                "Lost": "#e74c3c",
                "Open": "#f39c12"
            },
            barmode="stack"
        )
        fig.update_layout(xaxis_title="Account Manager", yaxis_title="Number of Opportunities")
        st.plotly_chart(fig)
        
        # Win Rate by Account Manager
        st.subheader("Win Rate by Account Manager")
        
        # Filter for meaningful win rates (managers with at least 5 closed opportunities)
        win_rate_df = am_pivot[(am_pivot['Won'] + am_pivot['Lost']) >= 5].copy()
        win_rate_df = win_rate_df.sort_values('Win_Rate', ascending=False)
        
        if not win_rate_df.empty:
            fig = px.bar(
                win_rate_df.reset_index(),
                x="AccountManager",
                y="Win_Rate",
                title="Win Rate by Account Manager (Minimum 5 Closed Opportunities)",
                text="Win_Rate",
                color="Win_Rate",
                color_continuous_scale=px.colors.sequential.Viridis
            )
            fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig.update_layout(xaxis_title="Account Manager", yaxis_title="Win Rate (%)")
            st.plotly_chart(fig)
        else:
            st.info("Not enough data to calculate meaningful win rates by account manager.")
        
        # Show data table
        if show_data_table:
            st.subheader("Account Manager Breakdown")
            display_df = am_pivot.reset_index()
            
            # Format the table
            if show_percentages:
                display_df = display_df[['AccountManager', 'Won', 'Won_Pct', 'Lost', 'Lost_Pct', 'Open', 'Open_Pct', 'Total', 'Win_Rate']]
                display_df.columns = ['Account Manager', 'Won', 'Won %', 'Lost', 'Lost %', 'Open', 'Open %', 'Total', 'Win Rate %']
            else:
                display_df = display_df[['AccountManager', 'Won', 'Lost', 'Open', 'Total', 'Win_Rate']]
                display_df.columns = ['Account Manager', 'Won', 'Lost', 'Open', 'Total', 'Win Rate %']
            
            st.dataframe(display_df)
    
    # Renewal Type Analysis
    st.header("Breakdown by Renewal Type")
    
    # Get counts by renewal type and status
    rt_status_df = df.groupby(['RenewalType', 'StatusCategory']).size().reset_index(name='Count')
    
    # Stacked bar chart
    fig = px.bar(
        rt_status_df,
        x="RenewalType",
        y="Count",
        color="StatusCategory",
        title="Renewal Status by Type",
        color_discrete_map={
            "Won": "#2ecc71", 
            "Lost": "#e74c3c",
            "Open": "#f39c12"
        },
        barmode="stack"
    )
    fig.update_layout(xaxis_title="Renewal Type", yaxis_title="Number of Opportunities")
    st.plotly_chart(fig)
    
    # Combined Analysis
    if view_by == "Both":
        st.header("Combined Analysis: Line of Business & Account Manager")
        
        # Get top 5 account managers and top 5 lines of business
        top_am = am_pivot.head(5).index.tolist()
        top_lob = lob_pivot.head(5).index.tolist()
        
        # Filter data for heatmap
        combined_filter = (df['AccountManager'].isin(top_am)) & (df['BusinessType'].isin(top_lob))
        combined_df = df[combined_filter]
        
        # Create cross-tabulation for heatmap
        if not combined_df.empty:
            cross_tab = pd.crosstab(
                combined_df['AccountManager'], 
                combined_df['BusinessType'],
                normalize=False
            )
            
            # Heatmap
            fig = px.imshow(
                cross_tab,
                text_auto=True,
                aspect="auto",
                title="Opportunity Count: Top Account Managers by Top Lines of Business",
                color_continuous_scale=px.colors.sequential.Viridis
            )
            fig.update_layout(
                xaxis_title="Line of Business",
                yaxis_title="Account Manager"
            )
            st.plotly_chart(fig)
        else:
            st.info("Not enough data for combined analysis.")
    
    # Monthly trend analysis
    st.header("Monthly Renewal Trends")
    
    # Add month column to the DataFrame
    df['Month'] = pd.to_datetime(df['CloseDate']).dt.strftime('%Y-%m')
    
    # Get counts by month and status
    monthly_df = df.groupby(['Month', 'StatusCategory']).size().reset_index(name='Count')
    
    # Create line chart
    fig = px.line(
        monthly_df,
        x="Month",
        y="Count",
        color="StatusCategory",
        title="Monthly Renewal Status Trends",
        markers=True,
        color_discrete_map={
            "Won": "#2ecc71", 
            "Lost": "#e74c3c",
            "Open": "#f39c12"
        }
    )
    fig.update_layout(xaxis_title="Month", yaxis_title="Number of Opportunities")
    st.plotly_chart(fig)
    
    # Show full raw data option
    with st.expander("View Raw Data", expanded=False):
        st.dataframe(df)

else:
    st.warning("No data available for the selected date range. Please adjust your filters or check your Salesforce connection.")
