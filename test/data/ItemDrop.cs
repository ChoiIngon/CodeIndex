using System;
using System.Collections.Generic;

namespace GameServer.Items
{
    public class Modify
    {
    }
    
    public class DropEntry
    {
        public int ItemId { get; set; }
        public float DropRate { get; set; }
        public int MinQuantity { get; set; } = 1;
        public int MaxQuantity { get; set; } = 1;
    }

    public static class ItemDropSystem
    {
        private static readonly Random _rng = new Random();

        public static List<(int itemId, int qty)> RollDrops(int monsterId, List<DropEntry> table)
        {
            var result = new List<(int, int)>();
            foreach (var entry in table)
            {
                if (_rng.NextDouble() < entry.DropRate)
                {
                    int qty = _rng.Next(entry.MinQuantity, entry.MaxQuantity + 1);
                    result.Add((entry.ItemId, qty));
                }
            }
            return result;
        }

        public static float CalculateDropRate(float baseRate, float dropRateBonus)
        {
            float adjusted = baseRate * (1.0f + dropRateBonus);
            return Math.Min(adjusted, 1.0f);
        }

        public static void DropItem(int itemId, int quantity, float x, float y, int mapId)
        {
            var dropInfo = new DroppedItem
            {
                ItemId = itemId,
                Quantity = quantity,
                PosX = x,
                PosY = y,
                MapId = mapId,
                ExpireAt = DateTime.UtcNow.AddMinutes(5),
            };
            DroppedItemManager.Register(dropInfo);
        }
    }

    public class DroppedItem
    {
        public int ItemId { get; set; }
        public int Quantity { get; set; }
        public float PosX { get; set; }
        public float PosY { get; set; }
        public int MapId { get; set; }
        public DateTime ExpireAt { get; set; }
    }

    public static class DroppedItemManager
    {
        private static readonly List<DroppedItem> _items = new();
        public static void Register(DroppedItem item) => _items.Add(item);
    }
}
