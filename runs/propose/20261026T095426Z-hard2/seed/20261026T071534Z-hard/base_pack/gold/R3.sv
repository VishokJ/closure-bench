`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b0;
  logic [15:0] prescale = 16'd2;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid, busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  int ovr_cnt = 0;
  int fe_cnt = 0;
  logic [7:0] ovr_tdata = 8'h00;
  logic ovr_tvalid = 1'b0;

  always @(negedge clk) begin
    if (overrun_error) begin
      ovr_cnt++;
      ovr_tdata = m_axis_tdata;
      ovr_tvalid = m_axis_tvalid;
    end
    if (frame_error) fe_cnt++;
  end

  task automatic send_byte(input logic [7:0] b);
    int bit_clks;
    bit_clks = int'(prescale) * 8;
    rxd = 1'b0; repeat (bit_clks) @(negedge clk);
    for (int i = 0; i < 8; i++) begin
      rxd = b[i]; repeat (bit_clks) @(negedge clk);
    end
    rxd = 1'b1; repeat (bit_clks) @(negedge clk);
  endtask

  initial begin
    @(negedge clk);
    rst = 1'b1; repeat (2) @(negedge clk);
    rst = 1'b0; repeat (2) @(negedge clk);

    // First word, left unread (tready held low)
    send_byte(8'h3C);
    repeat (4) @(negedge clk);
    if (!(m_axis_tvalid && m_axis_tdata == 8'h3C))
      $fatal(1, "first word not presented: tvalid=%b tdata=%02h", m_axis_tvalid, m_axis_tdata);
    if (ovr_cnt != 0) $fatal(1, "unexpected overrun after first word");

    // Second word arrives while the first is pending
    send_byte(8'hA5);
    repeat (4) @(negedge clk);
    if (ovr_cnt != 1) $fatal(1, "expected exactly one overrun_error pulse, got %0d", ovr_cnt);
    if (!ovr_tvalid) $fatal(1, "m_axis_tvalid not high during overrun");
    if (ovr_tdata != 8'hA5) $fatal(1, "tdata during overrun = %02h, expected A5", ovr_tdata);
    if (!(m_axis_tvalid && m_axis_tdata == 8'hA5))
      $fatal(1, "after overrun: tvalid=%b tdata=%02h", m_axis_tvalid, m_axis_tdata);
    if (overrun_error) $fatal(1, "overrun_error stuck high");
    if (fe_cnt != 0) $fatal(1, "unexpected frame_error");

    // Consume the word
    m_axis_tready = 1'b1;
    @(negedge clk);
    m_axis_tready = 1'b0;
    if (m_axis_tvalid) $fatal(1, "tvalid did not drop after handshake");

    $display("PASS overrun");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
