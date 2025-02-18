# Order Calculator App

A Streamlit application for managing meat processing orders, inventory tracking, and production planning.

## Features

- **Order Calculator**: Calculate raw material requirements based on finished goods orders
- **Inventory Tracking**: Track raw material inventory and production records
- **Dashboard**: View order history and production metrics
- **Order Planning**: Create and manage purchase orders with multiple line items
- **Order Board**: Track order status through the production process

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd OrderCalculatorApp
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
Create a `.env` file in the project root with:
```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

## Usage

1. Start the Streamlit app:
```bash
streamlit run app.py
```

2. Navigate to http://localhost:8501 in your browser

## Pages

1. **Calculator**
   - Enter purchase order quantities
   - View raw material requirements
   - Calculate yields and related products

2. **Inventory Tracking**
   - Record raw material receipts
   - Log production records
   - Track inventory levels

3. **Dashboard**
   - View production history
   - Monitor yield performance
   - Track inventory movements

4. **Order Planning**
   - Create new purchase orders
   - Add multiple line items
   - Calculate costs and requirements

5. **Order Board**
   - Track order status
   - Update order progress
   - Filter and search orders

## Database Schema

The application uses Supabase with the following tables:

1. `inventory`: Tracks raw material inventory
   - Material receipts and adjustments
   - Cost tracking
   - Transaction history

2. `production`: Records production data
   - Input/output quantities
   - Yield calculations
   - PO number tracking

3. `orders`: Manages purchase orders
   - Multiple line items
   - Order status tracking
   - Cost calculations

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
