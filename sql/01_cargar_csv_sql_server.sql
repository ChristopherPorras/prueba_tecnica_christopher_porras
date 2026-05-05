/*
  Prueba tecnica retail - Paso 01
  Carga los seis CSV desde data/raw hacia SQL Server.

  Como usar:
  1. Ejecuta primero sql/00_crear_tablas_sql_server.sql.
  2. Cambia @data_path por la ruta ABSOLUTA de la carpeta data/raw en tu computadora.
     Ejemplo Windows:
       N'C:\Users\tu_usuario\Documents\prueba_tecnica_christopher_porras\data\raw\'
  3. Ejecuta este archivo completo desde la extension MSSQL de VS Code.

  Si BULK INSERT no puede leer tu carpeta, no es error del SQL: SQL Server lee archivos
  desde la maquina donde corre el servidor, no desde VS Code. En ese caso usa el asistente
  "Import Flat File" de la extension MSSQL o copia los CSV a una ruta accesible para el servidor.
*/

USE RetailPruebaTecnica;
GO

DECLARE @data_path NVARCHAR(4000) = N'C:\CAMBIA_ESTA_RUTA\prueba_tecnica_christopher_porras\data\raw\';
DECLARE @sql NVARCHAR(MAX);

DROP TABLE IF EXISTS dbo.stg_vendors;
DROP TABLE IF EXISTS dbo.stg_products;
DROP TABLE IF EXISTS dbo.stg_stores;
DROP TABLE IF EXISTS dbo.stg_transactions;
DROP TABLE IF EXISTS dbo.stg_transaction_items;
DROP TABLE IF EXISTS dbo.stg_store_promotions;

CREATE TABLE dbo.stg_vendors (
  vendor_id NVARCHAR(100),
  vendor_name NVARCHAR(200),
  country NVARCHAR(100),
  tier NVARCHAR(100),
  is_shared_catalog NVARCHAR(100)
);

CREATE TABLE dbo.stg_products (
  item_id NVARCHAR(100),
  item_name NVARCHAR(200),
  brand NVARCHAR(100),
  vendor_id NVARCHAR(100),
  category NVARCHAR(100),
  department NVARCHAR(100),
  cost NVARCHAR(100)
);

CREATE TABLE dbo.stg_stores (
  store_id NVARCHAR(100),
  store_name NVARCHAR(200),
  country NVARCHAR(100),
  city NVARCHAR(100),
  format NVARCHAR(100),
  size_sqm NVARCHAR(100),
  opening_date NVARCHAR(100),
  region NVARCHAR(100)
);

CREATE TABLE dbo.stg_transactions (
  transaction_id NVARCHAR(100),
  customer_id NVARCHAR(100),
  transaction_date NVARCHAR(100),
  store_id NVARCHAR(100),
  total_amount NVARCHAR(100),
  payment_method NVARCHAR(100),
  loyalty_card NVARCHAR(100),
  status NVARCHAR(100)
);

CREATE TABLE dbo.stg_transaction_items (
  transaction_item_id NVARCHAR(100),
  transaction_id NVARCHAR(100),
  item_id NVARCHAR(100),
  quantity NVARCHAR(100),
  unit_price NVARCHAR(100),
  was_on_promo NVARCHAR(100)
);

CREATE TABLE dbo.stg_store_promotions (
  store_id NVARCHAR(100),
  promo_name NVARCHAR(200),
  variant NVARCHAR(100),
  start_date NVARCHAR(100),
  end_date NVARCHAR(100),
  promo_type NVARCHAR(100)
);

SET @sql = N'BULK INSERT dbo.stg_vendors FROM ''' + @data_path + N'vendors.csv''
WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDQUOTE = ''"'', CODEPAGE = ''65001'', TABLOCK);';
EXEC sys.sp_executesql @sql;

SET @sql = N'BULK INSERT dbo.stg_products FROM ''' + @data_path + N'products.csv''
WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDQUOTE = ''"'', CODEPAGE = ''65001'', TABLOCK);';
EXEC sys.sp_executesql @sql;

SET @sql = N'BULK INSERT dbo.stg_stores FROM ''' + @data_path + N'stores.csv''
WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDQUOTE = ''"'', CODEPAGE = ''65001'', TABLOCK);';
EXEC sys.sp_executesql @sql;

SET @sql = N'BULK INSERT dbo.stg_transactions FROM ''' + @data_path + N'transactions.csv''
WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDQUOTE = ''"'', CODEPAGE = ''65001'', TABLOCK);';
EXEC sys.sp_executesql @sql;

SET @sql = N'BULK INSERT dbo.stg_transaction_items FROM ''' + @data_path + N'transaction_items.csv''
WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDQUOTE = ''"'', CODEPAGE = ''65001'', TABLOCK);';
EXEC sys.sp_executesql @sql;

SET @sql = N'BULK INSERT dbo.stg_store_promotions FROM ''' + @data_path + N'store_promotions.csv''
WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDQUOTE = ''"'', CODEPAGE = ''65001'', TABLOCK);';
EXEC sys.sp_executesql @sql;

TRUNCATE TABLE dbo.vendors;
TRUNCATE TABLE dbo.products;
TRUNCATE TABLE dbo.stores;
TRUNCATE TABLE dbo.transactions;
TRUNCATE TABLE dbo.transaction_items;
TRUNCATE TABLE dbo.store_promotions;

INSERT INTO dbo.vendors (vendor_id, vendor_name, country, tier, is_shared_catalog)
SELECT
  vendor_id,
  vendor_name,
  country,
  tier,
  CASE WHEN UPPER(is_shared_catalog) IN ('TRUE', '1', 'YES') THEN 1 ELSE 0 END
FROM dbo.stg_vendors;

INSERT INTO dbo.products (item_id, item_name, brand, vendor_id, category, department, cost)
SELECT
  item_id,
  item_name,
  brand,
  vendor_id,
  category,
  department,
  TRY_CONVERT(DECIMAL(18, 2), cost)
FROM dbo.stg_products;

INSERT INTO dbo.stores (store_id, store_name, country, city, format, size_sqm, opening_date, region)
SELECT
  store_id,
  store_name,
  country,
  city,
  format,
  TRY_CONVERT(INT, size_sqm),
  TRY_CONVERT(DATE, opening_date),
  region
FROM dbo.stg_stores;

INSERT INTO dbo.transactions (transaction_id, customer_id, transaction_date, store_id, total_amount, payment_method, loyalty_card, status)
SELECT
  transaction_id,
  NULLIF(customer_id, ''),
  TRY_CONVERT(DATE, transaction_date),
  store_id,
  TRY_CONVERT(DECIMAL(18, 2), total_amount),
  payment_method,
  CASE WHEN UPPER(loyalty_card) IN ('TRUE', '1', 'YES') THEN 1 ELSE 0 END,
  status
FROM dbo.stg_transactions;

INSERT INTO dbo.transaction_items (transaction_item_id, transaction_id, item_id, quantity, unit_price, was_on_promo)
SELECT
  transaction_item_id,
  transaction_id,
  item_id,
  TRY_CONVERT(INT, quantity),
  TRY_CONVERT(DECIMAL(18, 2), unit_price),
  CASE WHEN UPPER(was_on_promo) IN ('TRUE', '1', 'YES') THEN 1 ELSE 0 END
FROM dbo.stg_transaction_items;

INSERT INTO dbo.store_promotions (store_id, promo_name, variant, start_date, end_date, promo_type)
SELECT
  store_id,
  promo_name,
  variant,
  TRY_CONVERT(DATE, start_date),
  TRY_CONVERT(DATE, end_date),
  promo_type
FROM dbo.stg_store_promotions;
GO
