-- Drop existing triggers first
drop trigger if exists update_inventory_purchases_updated_at on inventory_purchases;
drop trigger if exists update_inventory_after_purchase on inventory_purchases;
drop trigger if exists update_inventory_after_production on production;

-- Create inventory table if it doesn't exist
create table if not exists inventory (
    id uuid default uuid_generate_v4() primary key,
    material text not null unique,
    quantity numeric not null default 0,
    last_updated timestamp with time zone default now(),
    created_at timestamp with time zone default now()
);

-- Create inventory_purchases table if it doesn't exist
create table if not exists inventory_purchases (
    id uuid default uuid_generate_v4() primary key,
    material text not null references inventory(material),
    quantity numeric not null,
    cost numeric(10,2) not null,
    purchase_date date not null,
    transaction_type text not null,
    price_per_lb numeric(10,4) not null,
    invoice_number text not null,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- Create production table if it doesn't exist
create table if not exists production (
    id uuid default uuid_generate_v4() primary key,
    input_material text not null references inventory(material),
    input_quantity numeric not null,
    created_at timestamp with time zone default now()
);

-- Create an updated_at trigger
create or replace function update_updated_at_column()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger update_inventory_purchases_updated_at
    before update on inventory_purchases
    for each row
    execute function update_updated_at_column();

-- Create trigger to update inventory quantities
create or replace function update_inventory_quantity()
returns trigger as $$
begin
    -- For new purchases
    if TG_OP = 'INSERT' then
        -- Try to update existing inventory
        update inventory
        set quantity = quantity + NEW.quantity,
            last_updated = now()
        where material = NEW.material;
        
        -- If no row was updated, insert new material
        if not found then
            insert into inventory (material, quantity)
            values (NEW.material, NEW.quantity);
        end if;
    end if;
    
    return NEW;
end;
$$ language plpgsql;

create trigger update_inventory_after_purchase
    after insert on inventory_purchases
    for each row
    execute function update_inventory_quantity();

-- Create trigger to update inventory quantities from production
create or replace function update_inventory_from_production()
returns trigger as $$
begin
    -- Subtract the input quantity from inventory
    update inventory
    set 
        quantity = quantity - NEW.input_quantity,
        last_updated = now()
    where material = NEW.input_material;
    
    -- Raise an error if inventory would go negative
    if not found or (
        select quantity < 0 
        from inventory 
        where material = NEW.input_material
    ) then
        raise exception 'Insufficient inventory for material: %', NEW.input_material;
    end if;
    
    return NEW;
end;
$$ language plpgsql;

-- Drop existing trigger if it exists
drop trigger if exists update_inventory_after_production on production;

-- Create trigger for production table
create trigger update_inventory_after_production
    after insert on production
    for each row
    execute function update_inventory_from_production();

-- Initialize inventory with unique materials
insert into inventory (material, quantity)
select distinct material, 0
from (values 
    ('2PC CHUCK'),
    ('OUTSIDE SKIRT'),
    ('RIBEYE'),
    ('SHORT RIB'),
    ('BRISKET'),
    ('TRIM')
) as m(material)
on conflict (material) do nothing;

-- Insert data from the CSV
insert into inventory_purchases 
    (material, quantity, cost, purchase_date, transaction_type, price_per_lb, invoice_number)
values
    ('2PC CHUCK', 9951.3, 40501.79, '2024-09-26', 'purchase', 4.0700, '86380'),
    ('OUTSIDE SKIRT', 511.4, 4165.66, '2024-09-26', 'purchase', 8.1456, '86380'),
    ('RIBEYE', 3336.8, 31117.66, '2024-09-26', 'purchase', 9.3256, '86380'),
    ('SHORT RIB', 2111.2, 14096.69, '2024-09-26', 'purchase', 6.6771, '86380'),
    ('BRISKET', 8393.0, 31478.79, '2024-09-26', 'purchase', 3.7506, '86380'),
    ('OUTSIDE SKIRT', 733.7, 6456.56, '2024-11-25', 'purchase', 8.8000, '86945'),
    ('OUTSIDE SKIRT', 1988.9, 17502.32, '2024-11-25', 'purchase', 8.8000, '86945'),
    ('OUTSIDE SKIRT', 548.1, 4823.28, '2024-12-02', 'purchase', 8.8000, '86999'),
    ('OUTSIDE SKIRT', 1796.4, 15808.32, '2024-12-02', 'purchase', 8.8000, '86999'),
    ('RIBEYE', 2609.9, 26668.74, '2024-12-09', 'purchase', 10.2183, '87056'),
    ('BRISKET', 8568.1, 32952.91, '2024-12-09', 'purchase', 3.8460, '87056'),
    ('2PC CHUCK', 9834.1, 36267.18, '2024-12-09', 'purchase', 3.6879, '87056'),
    ('OUTSIDE SKIRT', 1986.7, 17482.96, '2024-12-27', 'purchase', 8.8000, '87252'),
    ('OUTSIDE SKIRT', 743.5, 6542.80, '2024-12-09', 'purchase', 8.8000, '87058'),
    ('BRISKET', 10140.9, 39710.75, '2025-02-17', 'purchase', 3.9159, '87765'),
    ('OUTSIDE SKIRT', 2531.6, 22278.08, '2024-12-09', 'purchase', 8.8000, '87058'),
    ('OUTSIDE SKIRT', 3677.6, 32362.88, '2024-12-13', 'purchase', 8.8000, '87145'),
    ('OUTSIDE SKIRT', 3392.6, 29854.88, '2024-12-20', 'purchase', 8.8000, '87212'),
    ('RIBEYE', 6219.3, 61237.72, '2025-01-07', 'purchase', 9.8464, '87327'),
    ('RIBEYE', 995.7, 16030.77, '2025-01-07', 'purchase', 16.1000, 'Byproduct'),
    ('TRIM', 8656.0, 33239.04, '2025-01-15', 'purchase', 3.8400, 'Byproduct'),
    ('2PC CHUCK', 8520.3, 32334.54, '2025-01-20', 'purchase', 3.7950, '87485'),
    ('BRISKET', 3610.4, 15485.73, '2025-01-20', 'purchase', 4.2892, '87485'),
    ('TRIM', 1304.46, 5009.13, '2025-02-03', 'purchase', 3.8400, 'Byproduct');

-- Create indexes for better query performance
create index if not exists idx_inventory_material 
    on inventory(material);

create index if not exists idx_inventory_purchases_material 
    on inventory_purchases(material);

create index if not exists idx_inventory_purchases_purchase_date 
    on inventory_purchases(purchase_date);

create index if not exists idx_inventory_purchases_invoice_number 
    on inventory_purchases(invoice_number);

-- Create views for analysis
-- Monthly purchase totals by material
create or replace view monthly_purchases as
select 
    date_trunc('month', purchase_date) as month,
    material,
    sum(quantity) as total_quantity,
    sum(cost) as total_cost,
    avg(price_per_lb) as avg_price_per_lb
from inventory_purchases
group by date_trunc('month', purchase_date), material
order by month desc, material;

-- Current inventory levels with latest purchase price
create or replace view current_inventory as
select 
    i.material,
    i.quantity as current_quantity,
    i.last_updated,
    latest_purchase.price_per_lb as last_purchase_price,
    latest_purchase.purchase_date as last_purchase_date
from inventory i
left join lateral (
    select price_per_lb, purchase_date
    from inventory_purchases ip
    where ip.material = i.material
    order by purchase_date desc
    limit 1
) latest_purchase on true;

-- Create view that shows current inventory with production usage
create or replace view inventory_with_usage as
select 
    i.material,
    i.quantity as current_quantity,
    i.last_updated,
    coalesce(p.total_used, 0) as quantity_used_in_production,
    coalesce(ip.total_purchased, 0) as total_purchased,
    latest_purchase.price_per_lb as last_purchase_price,
    latest_purchase.purchase_date as last_purchase_date
from inventory i
left join (
    select 
        input_material,
        sum(input_quantity) as total_used
    from production
    group by input_material
) p on p.input_material = i.material
left join (
    select 
        material,
        sum(quantity) as total_purchased
    from inventory_purchases
    group by material
) ip on ip.material = i.material
left join lateral (
    select price_per_lb, purchase_date
    from inventory_purchases
    where material = i.material
    order by purchase_date desc
    limit 1
) latest_purchase on true;
