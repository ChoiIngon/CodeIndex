using System;
using System.Collections.Generic;

namespace GameServer.Character
{
    public class LevelUpEventArgs : EventArgs
    {
        public int PlayerId { get; set; }
        public int OldLevel { get; set; }
        public int NewLevel { get; set; }
    }

    public class LevelSystem
    {
        private static readonly int[] ExpTable = BuildExpTable();

        public event EventHandler<LevelUpEventArgs> LevelUpEvent;

        public void GainExperience(int playerId, ref int currentExp, ref int currentLevel, int expAmount)
        {
            currentExp += expAmount;

            while (currentLevel < ExpTable.Length && currentExp >= ExpTable[currentLevel])
            {
                currentExp -= ExpTable[currentLevel];
                int oldLevel = currentLevel;
                currentLevel++;
                OnLevelUp(playerId, oldLevel, currentLevel);
            }
        }

        protected virtual void OnLevelUp(int playerId, int oldLevel, int newLevel)
        {
            LevelUpEvent?.Invoke(this, new LevelUpEventArgs
            {
                PlayerId = playerId,
                OldLevel = oldLevel,
                NewLevel = newLevel,
            });

            GrantLevelUpRewards(playerId, newLevel);
        }

        private void GrantLevelUpRewards(int playerId, int newLevel)
        {
            int statPoints = newLevel % 10 == 0 ? 5 : 2;
            int skillPoints = 1;
        }

        public int ExpToNextLevel(int level)
        {
            if (level >= ExpTable.Length) return int.MaxValue;
            return ExpTable[level];
        }

        private static int[] BuildExpTable()
        {
            var table = new int[200];
            for (int i = 0; i < table.Length; i++)
                table[i] = (int)(100 * Math.Pow(1.15, i));
            return table;
        }
    }
}
