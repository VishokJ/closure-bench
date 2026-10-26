# illegal_stimulus: qwen/qwen3.8-27b

Rollout `qwen3.8-27b/T7/4` (/Users/vishokj/Developer/cb-probe/outputs/official/qwen/closure-bench--qwen--qwen3.8-27b--null--ec46d01c/traces.jsonl:171), task T7, grade status `illegal_stimulus`. Picked as the median submission length (2079 chars) of 15 rollouts in this category for this model.

Sub-label: `axis_tvalid_held`

## Evidence

```json
{
 "checker": "TOP.tb.dut.uart_tx_inst.u_chk_legal",
 "diagnostic": "ILLEGAL_STIMULUS: axis_tvalid_held at 612000 in TOP.tb.dut.uart_tx_inst.u_chk_legal",
 "time": 612000
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 157, input_changes 3, bound 300, witness f796c55e34ea2404
// Formal witness for T7_tvalid_first_clock_after_reset (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (157 cycles), replayed on the uart_tx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic [7:0] s_axis_tdata = 8'd165;
  logic s_axis_tvalid = 1'd0;
  logic [15:0] prescale = 16'd1;
  wire  s_axis_tready;
  wire  txd;
  wire  busy;

  uart_tx dut (.clk(clk), .rst(rst), .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid), .prescale(prescale), .s_axis_tready(s_axis_tready), .txd(txd), .busy(busy));

  initial begin
    @(negedge clk);
    rst = 1'd0; s_axis_tvalid = 1'd1;
    repeat (2) @(negedge clk);
    s_axis_tdata = 8'd60;
    repeat (155) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
`timescale 1ns / 1ps

module tb;
  localparam int CLK_PERIOD = 8;
  localparam logic [15:0] PRESCALE = 16'd1;

  logic        clk = 1'b0;
  logic        rst = 1'b1;
  logic [7:0]  s_axis_tdata = 8'h00;
  logic        s_axis_tvalid = 1'b0;
  logic [15:0] prescale = PRESCALE;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;

  wire         s_axis_tready;
  wire [7:0]   m_axis_tdata;
  wire         m_axis_tvalid;
  wire         txd;
  wire         tx_busy;
  wire         rx_busy;
  wire         rx_overrun_error;
  wire         rx_frame_error;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart dut (
    .clk(clk),
    .rst(rst),
    .s_axis_tdata(s_axis_tdata),
    .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .m_axis_tdata(m_axis_tdata),
    .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .txd(txd),
    .tx_busy(tx_busy),
    .rx_busy(rx_busy),
    .rx_overrun_error(rx_overrun_error),
    .rx_frame_error(rx_frame_error),
    .prescale(prescale)
  );

  initial begin
    // Let reset be sampled on at least two rising edges.
    repeat (2) @(negedge clk);

    // Release reset and present the first byte on the very first clock
    // after reset falls.  s_axis_tready is still low from reset.
    rst = 1'b0;
    s_axis_tdata = 8'hA5;
    s_axis_tvalid = 1'b1;

    // AXI-Stream requires tvalid to remain asserted for the next clock
    // because tready was low on the previous rising edge.
    repeat (2) @(negedge clk);
    s_axis_tvalid = 1'b0;

    // Wait until the first frame has fully completed and the transmitter
    // is idle with tready high.  With prescale = 1, this is the negedge
    // before the 73rd rising edge after the first load.
    repeat (71) @(negedge clk);
    s_axis_tdata = 8'h3C;
    s_axis_tvalid = 1'b1;

    // One handshake cycle is enough for the second byte.
    repeat (1) @(negedge clk);
    s_axis_tvalid = 1'b0;

    // Allow the second frame to shift out and the cover point to be hit.
    repeat (200) @(negedge clk);
    $finish;
  end

endmodule
```
