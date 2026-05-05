### Rides
Rides are the core of your amusement park. They are the primary driver in determining how many guests visit your park, they improve guest happiness, and contribute to the overall value of the park. Rides have several key attributes:
- **Capacity:** How many guests can fit on the ride at one time. Capacity also affects how frequently the ride operates. The cumulative capacity of your park is also a key factor in how many guests visit the park.
- **Excitement:** How thrilling the ride is. Higher excitement scores increase guest happiness and park rating.
- **Intensity:** How intense the ride experience is. Keeping the average intensity balanced (around 5) ensures your park caters to a wide range of guests and improves your rating.
- **Ticket price:** The amount guests must pay to ride. If a guest cannot afford the ticket, they are rejected, which decreases their happiness. Each ride has a `max_ticket_price` hard limit in `rides_economics.md` — the simulator **immediately rejects** any place or modify action whose price exceeds this value; no partial acceptance, no rounding down. Always set price equal to `max_ticket_price` on placement (start at the cap, tune down only if guests stop coming).
- **Cost per operation:** The amount it costs each time the ride runs.

> **TIP:** Building multiple rides of the same kind (i.e., identical subtype and subclass) yields diminishing returns for your park rating. Diversifying your attractions will lead to a higher overall rating.

Rides only operate if guests have boarded. After the first guest boards, rides wait a few turns to allow more guests to join. This waiting time is longer for rides with higher capacity but decreases as more guests board. A full ride always operates immediately.

Rides may break down after operating. When broken, they are out of service and will turn away guests, negatively affecting their happiness and your park rating.  
> **TIP:** Hire mechanics to fix broken rides promptly.

There are three subtypes of rides:
- **Carousels:** Cheap to build and operate, and they rarely break down. However, they provide limited excitement and capacity.
- **Ferris Wheels:** Intermediate rides with the highest capacities among all subtypes.
- **Roller Coasters:** Expensive but high-value rides that offer the highest excitement and intensity scores, at the cost of frequent breakdowns.

## Ride Notes

- Any existing ride can be sold for a fraction of its building cost.
- A ride that breaks down incurs a repair cost equal to a fraction of its building cost.
- Per-tier numeric stats (building cost, capacity, max_ticket_price, excitement, intensity, breakdown rate) are in `rides_economics.md` — always query ConfigRag for the specific subtype+tier before proposing a price.
