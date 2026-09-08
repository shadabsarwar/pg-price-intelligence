import type { DataStatus, Product } from "./product";
import { isProduct } from "./product";

export interface ProductPrice {
  product: Product;
  best_price: number | null;
  highest_price: number | null;
  normalized_price: number | null;
  normalized_unit: string | null;
  platforms_found: number;
  data_source: string;
  data_status: DataStatus;
  last_updated: string | null;
}

export interface CompetitorMatch extends ProductPrice {
  match_confidence: number;
  match_breakdown: Record<string, number>;
  match_explanation: string;
  price_difference: number | null;
  percentage_difference: number | null;
  normalized_difference: number | null;
  normalized_percentage_difference: number | null;
  comparable_prices: boolean;
  highlights: string[];
}

export interface CompetitorComparison {
  pg_product: ProductPrice;
  competitors: CompetitorMatch[];
  competitor_companies: { id: string; name: string }[];
  market_position: {
    basis: string;
    normalized_unit: string | null;
    pg_price: number | null;
    pg_normalized_price: number | null;
    market_average: number | null;
    cheapest_competitor: number | null;
    percentage_above_market: number | null;
    comparable_competitor_count: number;
    data_status: DataStatus;
  };
  data_status: DataStatus;
  last_updated: string | null;
}

const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object";
const finite = (value: unknown) => typeof value === "number" && Number.isFinite(value);
const nullableNumber = (value: unknown) => value === null || finite(value);
const status = (value: unknown) => ["LIVE", "VERIFIED", "STALE", "DEMO", "ERROR", "IMPORTED", "MANUAL", "COLLECTED", "UNAVAILABLE"].includes(String(value));
const timestamp = (value: unknown) => value === null || (typeof value === "string" && Number.isFinite(Date.parse(value)));

function isPrice(value: unknown): boolean {
  return record(value) && isProduct(value.product)
    && ["best_price", "highest_price", "normalized_price"].every(key => nullableNumber(value[key]))
    && (value.normalized_unit === null || typeof value.normalized_unit === "string")
    && finite(value.platforms_found) && typeof value.data_source === "string"
    && status(value.data_status) && timestamp(value.last_updated);
}

export function isCompetitorComparison(value: unknown): value is CompetitorComparison {
  if (!record(value) || !isPrice(value.pg_product) || !Array.isArray(value.competitors) || !record(value.market_position)) return false;
  const market = value.market_position;
  return value.competitors.every(item => record(item) && isPrice(item) && finite(item.match_confidence)
    && record(item.match_breakdown) && Object.values(item.match_breakdown).every(finite)
    && typeof item.match_explanation === "string" && typeof item.comparable_prices === "boolean"
    && ["price_difference", "percentage_difference", "normalized_difference", "normalized_percentage_difference"].every(key => nullableNumber(item[key]))
    && Array.isArray(item.highlights) && item.highlights.every(label => typeof label === "string"))
    && Array.isArray(value.competitor_companies) && value.competitor_companies.every(company => record(company) && typeof company.name === "string" && typeof company.id === "string")
    && ["pg_price", "pg_normalized_price", "market_average", "cheapest_competitor", "percentage_above_market"].every(key => nullableNumber(market[key]))
    && finite(market.comparable_competitor_count) && status(market.data_status)
    && (market.normalized_unit === null || typeof market.normalized_unit === "string")
    && typeof market.basis === "string" && status(value.data_status) && timestamp(value.last_updated);
}
