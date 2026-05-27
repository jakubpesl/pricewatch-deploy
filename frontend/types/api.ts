export interface DiscoveryJob {
  id: number;
  model_number: string;
  status: "pending" | "running" | "completed" | "failed" | "partial";
  retailers_found: number;
  sources_completed: string[] | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface ProductRetailerOut {
  id: number;
  retailer_name: string;
  retailer_domain: string;
  country_code: string;
  product_url: string;
  currency: string;
  current_price: number | null;
  original_price: number | null;
  in_stock: boolean | null;
  rating: number | null;
  review_count: number | null;
  screenshot_url: string | null;
  source: string;
  last_scraped_at: string | null;
}

export interface ProductOut {
  id: number;
  model_number: string;
  name: string | null;
  brand: string | null;
  category: string | null;
  ean: string | null;
  image_url: string | null;
  retailers: ProductRetailerOut[];
  created_at: string;
}

export interface PricePoint {
  retailer_id: number;
  retailer_name: string;
  country_code: string;
  price: number;
  currency: string;
  in_stock: boolean | null;
  observed_at: string;
}
