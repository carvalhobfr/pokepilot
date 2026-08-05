#!/bin/bash

# Script to reset specific agents to get different starter Pokemon
# Usage: ./reset_agents.sh [agent_names...]
# Example: ./reset_agents.sh HARON FARON DARON

echo "🔄 Agent Reset Script"
echo "===================="

# If no arguments, reset HARON, FARON, DARON by default
if [ $# -eq 0 ]; then
    AGENTS=("HARON" "FARON" "DARON")
    echo "No agents specified. Resetting default agents with non-Bulbasaur starters:"
    echo "  - HARON (Charmander)"
    echo "  - FARON (Squirtle)"
    echo "  - DARON (Bulbasaur)"
else
    AGENTS=("$@")
    echo "Resetting specified agents: ${AGENTS[@]}"
fi

echo ""

for agent in "${AGENTS[@]}"; do
    echo "Processing $agent..."
    
    # Delete checkpoints
    if [ -d "checkpoints/$agent" ]; then
        rm -rf "checkpoints/$agent"
        echo "  ✅ Deleted checkpoints for $agent"
    else
        echo "  ℹ️  No checkpoints found for $agent"
    fi
    
    # Delete task file
    if [ -f "tasks/$agent.txt" ]; then
        rm "tasks/$agent.txt"
        echo "  ✅ Deleted task file for $agent"
    fi
    
    echo ""
done

echo "✨ Reset complete!"
echo ""
echo "The agents will start fresh on next training run with their assigned starters:"
echo "  - Khalliss: Bulbasaur (Grass)"
echo "  - BARON: Charmander (Fire)"
echo "  - CARON: Squirtle (Water)"
echo "  - DARON: Bulbasaur (Grass)"
echo "  - EARON: Charmander (Fire)"
echo "  - FARON: Squirtle (Water)"
echo "  - GARON: Bulbasaur (Grass)"
echo "  - HARON: Charmander (Fire)"
echo ""
echo "Restart training to apply changes: ./start_all.sh"
