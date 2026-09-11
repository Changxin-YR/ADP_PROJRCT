"""阶段 4：日常养殖（作业 / 抽样 / 转塘 / 损耗）。"""
from __future__ import annotations

from datetime import datetime

PREFIX = "MT2609"


class ProductionFlows:
    def daily_farming(self) -> None:
        self.section("阶段 4：日常作业 / 抽样 / 转塘 / 损耗")
        production = "/api/v1/production"

        operations = (
            (f"{PREFIX}-OP-01", "清晨巡塘", {"operation_type": "patrol", "source_detail": {"water_quality": "水面平静", "fish_activity": "摄食活跃"}}),
            (f"{PREFIX}-OP-02", "水质检测", {"operation_type": "water_quality", "source_detail": {"temperature_c": 28.5, "ph": 7.6, "dissolved_oxygen_mg_l": 5.2}}),
            (f"{PREFIX}-OP-03", "换水 15cm", {"operation_type": "water_change", "source_detail": {"volume_m3": 120, "water_source": "北区东渠"}}),
        )
        for code, name, payload in operations:
            row = self.create(f"{production}/daily-operations", {
                "code": code, "name": name, "pond_id": self.ids["pond1"], "batch_id": self.ids["batch"],
                "happened_at": datetime.now().replace(microsecond=0).isoformat(), "payload": payload, "note": "自动验收",
            })
            self.check(f"日常作业 {name} 核验通过", self.advance(f"{production}/daily-operations", row)["status"] == "verified")

        self.expect_error(
            "反向：巡塘缺少关键参数被拒绝",
            lambda: self.create(f"{production}/daily-operations", {
                "code": f"{PREFIX}-OP-BAD", "name": "缺参数巡塘", "pond_id": self.ids["pond1"],
                "operation_type": "patrol", "payload": {"source_detail": {"water_quality": "正常"}},
            }),
            status=400, code="DAILY_OP_PARAM_REQUIRED",
        )

        for index, weight in ((1, 6.5), (2, 8.0)):
            row = self.create(f"{production}/samplings", {
                "code": f"{PREFIX}-SP-{index:02d}", "name": f"第 {index} 次规格抽样", "batch_id": self.ids["batch"],
                "pond_id": self.ids["pond1"], "quantity": 50, "weight_kg": weight,
                "happened_at": datetime.now().replace(microsecond=0).isoformat(), "note": "抛网抽样",
            })
            self.check(f"规格抽样 {index} 核验通过", self.advance(f"{production}/samplings", row)["status"] == "verified")

        transfer = self.create(f"{production}/transfers", {
            "code": f"{PREFIX}-TR-01", "name": "1号塘分塘至2号塘", "batch_id": self.ids["batch"],
            "pond_id": self.ids["pond1"], "target_pond_id": self.ids["pond2"], "quantity": 5000, "weight_kg": 400,
            "happened_at": datetime.now().replace(microsecond=0).isoformat(), "note": "密度调节",
        })
        self.ids["transfer"] = int(transfer["id"])
        transfer = self.submit(f"{production}/transfers", transfer)
        self.expect_error(
            "反向：高风险转塘缺凭据核验被拒绝",
            lambda: self.verify(f"{production}/transfers", transfer),
            status=400, code="EVIDENCE_REQUIRED",
        )
        attachment = self.verifier.upload_attachment("production:transfers", transfer["id"])
        self.check(
            "转塘带凭据核验通过",
            self.verify(f"{production}/transfers", transfer, evidence=[attachment])["status"] == "verified",
        )

        loss = self.create(f"{production}/losses", {
            "code": f"{PREFIX}-LS-01", "name": "疾病损耗", "batch_id": self.ids["batch"], "pond_id": self.ids["pond1"],
            "quantity": 300, "weight_kg": 25, "happened_at": datetime.now().replace(microsecond=0).isoformat(),
            "reason": "白斑综合征早期，已消毒并减料",
        })
        self.ids["loss"] = int(loss["id"])
        self.check("损耗带凭据核验通过", self.advance(f"{production}/losses", loss, evidence=True)["status"] == "verified")

    def batch_lifecycle(self) -> None:
        """阶段 15：批次生命周期变更入口（新增）。后端守卫：存活体不得关闭、不得跳级。"""
        self.section("阶段 15：批次生命周期变更入口（新增）")
        _, body = self.writer.get(f"/api/v1/production/batches/{self.ids['batch']}")
        batch = body["data"]["record"]
        self.expect_error(
            "反向：批次仍有存塘量时禁止关闭",
            lambda: self.writer.post(
                f"/api/v1/production/batches/{self.ids['batch']}/status",
                {"expected_version": batch["version"], "batch_status": "closed", "reason": "验证存活体拦截"},
            ),
            status=409,
        )
        self.expect_error(
            "反向：批次非法状态跳变被拒绝",
            lambda: self.writer.post(
                f"/api/v1/production/batches/{self.ids['batch']}/status",
                {"expected_version": batch["version"], "batch_status": "closed", "reason": "跳过中间状态"},
            ),
            status=409,
        )
