// gold_source: formal
// closure_core.formal.cover_witness: depth 166, input_changes 2, bound 300, witness 7d28c2cf909eda76
// Formal witness for T10_two_stop_gaps_9_clocks_prescale1 (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (166 cycles), replayed on the uart_tx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic [7:0] s_axis_tdata = 8'd0;
  logic s_axis_tvalid = 1'd0;
  logic [15:0] prescale = 16'd1;
  wire  s_axis_tready;
  wire  txd;
  wire  busy;

  uart_tx dut (.clk(clk), .rst(rst), .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid), .prescale(prescale), .s_axis_tready(s_axis_tready), .txd(txd), .busy(busy));

  initial begin
    @(negedge clk);
    rst = 1'd0; s_axis_tvalid = 1'd1;
    repeat (166) @(negedge clk);
    $finish;
  end
endmodule
