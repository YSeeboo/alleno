"""BOM demand snapshots and output plans; never inventory or customer shipments."""
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship

from database import Base


class OrderMaterialDemand(Base):
    __tablename__ = "order_material_demand"

    id = Column(Integer, primary_key=True)
    order_item_id = Column(Integer, ForeignKey("order_item.id", ondelete="CASCADE"), nullable=False, index=True)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty_per_unit = Column(Numeric(18, 7), nullable=False)
    order_quantity = Column(Integer, nullable=False)
    unit = Column(String, nullable=True)

    __table_args__ = (UniqueConstraint("order_item_id", "part_id", name="uq_order_material_demand"),)


class MaterialProductionAllocation(Base):
    __tablename__ = "material_production_allocation"

    id = Column(Integer, primary_key=True)
    demand_id = Column(Integer, ForeignKey("order_material_demand.id", ondelete="CASCADE"), nullable=False, index=True)
    plating_order_item_id = Column(Integer, ForeignKey("plating_order_item.id"), index=True)
    handcraft_jewelry_item_id = Column(Integer, ForeignKey("handcraft_jewelry_item.id"), index=True)
    quantity = Column(Numeric(14, 4), nullable=False)
    demand = relationship(OrderMaterialDemand)

    @property
    def order_item_id(self):
        return self.demand.order_item_id

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_material_allocation_positive"),
        CheckConstraint("(plating_order_item_id IS NULL) <> (handcraft_jewelry_item_id IS NULL)",
                        name="ck_material_allocation_source_xor"),
        UniqueConstraint("demand_id", "plating_order_item_id", name="uq_material_allocation_plating"),
        UniqueConstraint("demand_id", "handcraft_jewelry_item_id", name="uq_material_allocation_handcraft"),
    )
