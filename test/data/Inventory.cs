using System;
using System.Collections.Generic;
using System.Linq;

namespace GameServer.Items
{
    public class ItemSlot
    {
        public int SlotIndex { get; set; }
        public int ItemId { get; set; }
        public int Quantity { get; set; }
        public bool IsEmpty => ItemId == 0;
    }

    public class Inventory
    {
        private readonly List<ItemSlot> _slots;
        private readonly int _maxSlots;

        public Inventory(int maxSlots = 100)
        {
            _maxSlots = maxSlots;
            _slots = Enumerable.Range(0, maxSlots)
                .Select(i => new ItemSlot { SlotIndex = i })
                .ToList();
        }

        public bool AddItem(int itemId, int quantity = 1)
        {
            var existing = _slots.FirstOrDefault(s => s.ItemId == itemId && !s.IsEmpty);
            if (existing != null)
            {
                existing.Quantity += quantity;
                return true;
            }

            var emptySlot = _slots.FirstOrDefault(s => s.IsEmpty);
            if (emptySlot == null) return false;

            emptySlot.ItemId = itemId;
            emptySlot.Quantity = quantity;
            return true;
        }

        public bool RemoveItem(int itemId, int quantity = 1)
        {
            var slot = _slots.FirstOrDefault(s => s.ItemId == itemId && s.Quantity >= quantity);
            if (slot == null) return false;

            slot.Quantity -= quantity;
            if (slot.Quantity == 0)
                slot.ItemId = 0;
            return true;
        }

        public ItemSlot FindItem(int itemId)
        {
            return _slots.FirstOrDefault(s => s.ItemId == itemId && !s.IsEmpty);
        }

        public int GetItemCount(int itemId)
        {
            return _slots.Where(s => s.ItemId == itemId).Sum(s => s.Quantity);
        }

        public bool HasItem(int itemId, int quantity = 1)
        {
            return GetItemCount(itemId) >= quantity;
        }

        public int FreeSlotCount => _slots.Count(s => s.IsEmpty);
    }
}
