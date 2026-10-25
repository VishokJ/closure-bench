// Pre-fix: reward 0 only by accident (plan_hits drops covers under uart_rx__D9). With
// DATA_WIDTH 9, this clean frame (no false start) hits a false-start cover written as
// `bit_cnt == 4'd10` (proposer smoke run, candidate c01). Now rejected: parameter override.
`timescale 1ns / 1ps
module tb;
  localparam logic [15:0] PRESCALE = 16'd5;
  logic clk = 0, rst = 0, rxd = 1;
  wire [8:0] m_axis_tdata;
  wire m_axis_tvalid, busy, overrun_error, frame_error;
  always #4 clk = ~clk;
  uart_rx #(.DATA_WIDTH(9)) dut (.clk(clk), .rst(rst), .m_axis_tdata(m_axis_tdata),
    .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(1'b1), .rxd(rxd), .busy(busy),
    .overrun_error(overrun_error), .frame_error(frame_error), .prescale(PRESCALE));
  task automatic wait_clks(input int n); repeat (n) @(negedge clk); endtask
  initial begin
    rst = 1; wait_clks(2); rst = 0; wait_clks(2);
    rxd = 0; wait_clks(40);                                   // start
    for (int i = 0; i < 9; i++) begin rxd = 9'h0A5 >> i; wait_clks(40); end
    rxd = 1; wait_clks(80);                                   // stop + idle
    $finish;
  end
endmodule
