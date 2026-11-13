data "google_compute_network" "default" {
  count   = var.use_memorystore ? 1 : 0
  project = var.project_id
  name    = "default"
}

resource "google_vpc_access_connector" "redis" {
  count         = var.use_memorystore ? 1 : 0
  project       = var.project_id
  region        = var.region
  name          = "${var.service_name}-redis"
  network       = data.google_compute_network.default[0].name
  ip_cidr_range = var.vpc_connector_cidr

  depends_on = [google_project_service.required]
}

resource "google_redis_instance" "redis" {
  count              = var.use_memorystore ? 1 : 0
  project            = var.project_id
  region             = var.region
  name               = "${var.service_name}-redis"
  tier               = var.redis_tier
  memory_size_gb     = var.redis_memory_size_gb
  authorized_network = data.google_compute_network.default[0].id

  depends_on = [google_project_service.required]
}
