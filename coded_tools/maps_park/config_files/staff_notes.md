### Staff
Staff are necessary for the smooth operation of your park, ensuring attractions run properly and guests remain satisfied. Multiple staff can occupy and work on the same tile at any given time. All staff have a daily salary, and some incur additional operating costs when performing tasks.

There are three subtypes of staff:
- **Janitors:** Move through the park toward dirty areas. When on dirty tiles, they clean them. Each cleaning action incurs an operating cost.
- **Mechanics:** Move toward rides that are broken down. When they reach a tile with a broken ride, they repair it. The time and operating cost of repairs depend on the ride's building cost and the mechanic(s) performing the repair.
- **Specialists:** Perform different roles based on subclass:
  - Yellow (Clowns): Increases the happiness of guests waiting in line.
  - Blue (Stockers): Restocks shops with low inventory.
  - Green (Park Criers): Informs guests about out-of-service or dirty attractions, as well as current line wait time for rides.
  - Red (Vendors): Provides food and drink to guests waiting in line.

## Staff Notes

Per-tier numeric stats (salary, clean rate, repair rate, etc.) are reported in the observation envelope.

### Janitors
Janitors clean a tile up to their cleaning threshold before moving to the next tile to clean. In addition to their salary, janitors incur a small per-cleaning-action cost in supplies.

- *Blue, green, and red janitors* move at double speed.
- *Red janitors* perform preventative cleaning, cleaning tiles above the normal maximum cleanliness of 1.0.

### Mechanics
- *Blue, green, and red mechanics* move at double speed.
- *Red mechanics* perform preventative maintenance — partially repairing a ride before it breaks, further reducing repair time.

### Specialists
- *Yellow (Clown):* moves between rides, increasing the happiness of guests waiting in line.
- *Blue (Stocker):* restocks shops when remaining inventory falls below a restock threshold. Walks to an entrance/exit, purchases a percentage of the daily order quantity, and carries it to the shop. Carries at most a fixed inventory cap; stops making new purchases in the last few actions of the day to avoid restocking right before closing.
- *Green (Crier):* moves between attractions, informing guests about cleanliness, out-of-service status, and current line wait times. This prevents guests from visiting out-of-service attractions and steers them toward cleaner attractions with shorter waits.
- *Red (Vendor):* moves between rides, providing food and drink to guests waiting in line. Vendors do not incur extra costs and do not generate extra profit from these activities.
