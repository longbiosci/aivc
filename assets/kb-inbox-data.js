/* 投稿口数据 —— 由 tools/publish_inbox.py 生成，禁止手改。
 * 线上投稿口提交后落到 GitHub 收件箱，由后台取件入库，处理结果写回本文件，
 * 文献页据此显示「已收录 / 处理中 / 需补充」。s ∈ done | wait | blocked。 */
var KBINBOX_STATUS = [];
