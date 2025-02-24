-- Drop existing views
drop view if exists inventory_with_usage;
drop view if exists production_history;

-- Create view that shows current inventory with production usage
create view inventory_with_usage as
select 
    i.material,
    i.quantity as current_quantity,
    i.last_updated,
    coalesce(p.total_used_in_production, 0) as quantity_used_in_production,
    coalesce(ip.total_purchased, 0) as total_purchased,
    latest_purchase.price_per_lb as last_purchase_price,
    latest_purchase.purchase_date as last_purchase_date
from inventory i
left join (
    -- Calculate total used in production for each material
    select 
        upper(input_material) as input_material,  -- Convert to uppercase
        sum(input_quantity) as total_used_in_production
    from production
    group by upper(input_material)  -- Group by uppercase version
) p on p.input_material = i.material  -- inventory.material is already uppercase
left join (
    -- Calculate total purchased for each material
    select 
        material,
        sum(quantity) as total_purchased
    from inventory_purchases
    group by material
) ip on ip.material = i.material
left join lateral (
    -- Get latest purchase price and date
    select price_per_lb, purchase_date
    from inventory_purchases
    where material = i.material
    order by purchase_date desc
    limit 1
) latest_purchase on true;

-- Create a view for production history with cost tracking
create view production_history as
select 
    p.*,
    i.price_per_lb as material_cost_per_lb,
    (p.input_quantity * i.price_per_lb) as total_material_cost,
    i.purchase_date as material_purchase_date
from production p
left join lateral (
    -- Get the price of the material at the time of production
    select price_per_lb, purchase_date
    from inventory_purchases
    where material = upper(p.input_material)  -- Convert production material to uppercase
    order by purchase_date desc
    limit 1
) i on true;
