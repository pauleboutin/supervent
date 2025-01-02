# Holiday E-commerce Traffic Simulation Configuration
# A work in progress for January 2025
This configuration will emulate a modern e-commerce platform using a microservices architecture, typically deployed across multiple cloud regions. The system represents a three-tier architecture with web/application servers (Apache & Express.js), caching layer (Redis/Memcached), and database clusters (MySQL), all behind load balancers.

## Event Volume and Cardinality<br/>
- Base traffic: 1,000 requests/minute (~1.4M daily)<br/>
- Peak multipliers up to 6x during Cyber Monday (~8.6M daily)<br/>
- High cardinality elements include:
- - Visitors (hundreds of thousands)
- - User sessions and shopping carts (millions)
- - Product SKUs (hundreds of thousands)
- - Geographic locations (thousands)
- - Device types and browsers (hundreds)
  
## Seasonal Pattern Narrative

The configuration tells a realistic story of holiday e-commerce traffic from November through December:

Starting November 1st, we see typical weekday/weekend patterns with lunch-hour spikes. As we approach Thanksgiving (Nov 28), there's a gradual buildup with "shopping at work" patterns. Thanksgiving Day shows minimal traffic until evening, when it spikes dramatically as people begin early Black Friday shopping online.

Black Friday (Nov 29) demonstrates classic patterns: midnight rush of deal-hunters, early morning lull, then sustained high traffic with increased error rates due to system stress. The "skeleton crew" factor realistically impacts incident response times.

Cyber Monday (Dec 2) shows the highest multiplier (6x) during work hours, with clear patterns of office workers shopping and mobile/desktop shifts throughout the day. System stress indicators increase (cache pressure, API latency).

Mid-December brings shipping deadline-driven spikes, especially December 20-21, with "panic buying" behavior clearly visible in cart abandonment rates and retry patterns. Christmas Eve shows last-minute gift card purchases, followed by Christmas Day's mobile-heavy gift card redemption spike.

The post-Christmas period realistically models returns processing load and inventory rebalancing patterns.

## Log Patterns
The configuration generates logs that mirror real-world patterns, not sanitized standards. It includes:

- Mixed format logs (some JSON, some structured text)
- Inconsistent field names across services
- Real-world error patterns and stack traces
- Authentication and session management artifacts
- Shopping cart abandonment patterns
- Payment processing flows
- Inventory level changes
- Customer service interaction spikes

The dataset intentionally mirrors the messy reality of production systems.

## Use Cases Wanted!
How do you use logs for observability, site reliability, capacity planning, product analysis -- whatever matters? I welcome specific examples for which to create log datasets.

- Additional real-world variables and patterns to simulate
- New error conditions and edge cases
- Integration with different logging systems


