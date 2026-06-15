# playbook_director

Park_director's rules of thumb. The episode checklist is a standard
fixed phase plan that memory_keeper resets each episode (preflight).

## Restrategize triggers
Call anthropologist(mode='restrategize', reason=<short>) when ANY hits:
- Periodic sweep: status.step % 10 == ((episode - 1) % 10) AND
  status.step ≥ 10 (offset rotates by episode so coverage shifts).
  Pass `episode` and `step` in the anthropologist `reason`.
- Cash trending toward 0 in last 3-5 turns
- 3+ consecutive turns of negative reward
- 2+ no-op turns reported by validator
- Specialist flags a big opportunity

## Learned rules
Confirmed hypotheses get folded here with a "(learned ep<N>)" tag;
memory_keeper weights the episode checklist toward them.
